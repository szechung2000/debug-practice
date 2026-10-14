"""Parallel, chunked load of one deal-month into the store."""
from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from . import reader, store, transform
from .config import LoadConfig

log = logging.getLogger(__name__)


class LoadError(Exception):
    pass


@dataclass
class LoadResult:
    run_id: str
    deal_id: str
    period: str
    file_rows: int = 0
    loaded_rows: int = 0
    replaced_rows: int = 0
    chunks_ok: int = 0
    failed_chunks: list[tuple[int, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed_chunks and self.loaded_rows == self.file_rows


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def prior_period_iso(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return date(y, m, 1).isoformat()


def _load_chunk(cfg: LoadConfig, chunk: reader.Chunk, priors: dict, deal_id: str, period_iso: str) -> int:
    rows = []
    for offset, line in enumerate(chunk.lines):
        try:
            rec = reader.parse_line(line)
        except reader.RecordError as exc:
            raise reader.RecordError(f"line {chunk.first_line + offset}: {exc}") from exc
        if rec["deal_id"] != deal_id or rec["reporting_period"] != period_iso:
            raise reader.RecordError(f"line {chunk.first_line + offset}: record for "
                                     f"{rec['deal_id']} {rec['reporting_period']} in {deal_id} {period_iso} file")
        rows.append(transform.to_db_row(transform.enrich(rec, priors.get(rec["loan_id"]))))
    # Each worker uses its own connection; sqlite3 connections are not shared across threads.
    with closing(store.connect(cfg.store_path, cfg.busy_timeout_ms)) as conn:
        with conn:
            return store.insert_rows(conn, rows)


def load_partition(cfg: LoadConfig, deal_id: str, period: str) -> LoadResult:
    """Load `<deal>_<YYYYMM>.txt` for `period` ('YYYY-MM')."""
    path = cfg.file_for(deal_id, period)
    if not path.exists():
        raise LoadError(f"vendor file not found: {path}")
    result = LoadResult(uuid.uuid4().hex[:12], deal_id, period, file_rows=reader.count_lines(path))
    period_iso = f"{period}-01"
    with closing(store.connect(cfg.store_path, cfg.busy_timeout_ms)) as conn:
        with conn:
            conn.execute("INSERT INTO load_runs (run_id, deal_id, period, file_name, file_rows, status, started_at) "
                         "VALUES (?, ?, ?, ?, ?, 'RUNNING', ?)",
                         (result.run_id, deal_id, period, path.name, result.file_rows, _now()))
            result.replaced_rows = store.delete_partition(conn, deal_id, period)
        priors = store.prior_upbs(conn, deal_id, prior_period_iso(period))
    log.info("run %s: %s %s, %d rows in %s, replacing partition (%d existing rows removed), %d prior UPBs",
             result.run_id, deal_id, period, result.file_rows, path.name, result.replaced_rows, len(priors))

    with ThreadPoolExecutor(max_workers=cfg.workers, thread_name_prefix="chunk") as pool:
        futures = {pool.submit(_load_chunk, cfg, ch, priors, deal_id, period_iso): ch.number
                   for ch in reader.iter_chunks(path, cfg.chunk_size)}
        for fut in as_completed(futures):
            number = futures[fut]
            try:
                result.loaded_rows += fut.result()
                result.chunks_ok += 1
            except Exception as exc:  # one bad chunk must not hide the others' errors
                result.failed_chunks.append((number, str(exc)))
                log.error("chunk %d failed: %s", number, exc)

    status = "OK" if result.ok else "FAILED"
    with closing(store.connect(cfg.store_path, cfg.busy_timeout_ms)) as conn:
        with conn:
            conn.execute("UPDATE load_runs SET loaded_rows=?, chunks_ok=?, chunks_failed=?, status=?, finished_at=? "
                         "WHERE run_id=?", (result.loaded_rows, result.chunks_ok, len(result.failed_chunks),
                                            status, _now(), result.run_id))
    log.info("run %s: %s, %d/%d rows loaded, %d chunks ok, %d failed", result.run_id, status,
             result.loaded_rows, result.file_rows, result.chunks_ok, len(result.failed_chunks))
    return result


def verify_partition(cfg: LoadConfig, deal_id: str, period: str) -> dict:
    """Post-load check: every loan in the vendor file is in the store."""
    path = cfg.file_for(deal_id, period)
    expected = reader.count_lines(path)
    with closing(store.connect(cfg.store_path, cfg.busy_timeout_ms)) as conn:
        stats = store.partition_stats(conn, deal_id, f"{period}-01")
    stats["file_rows"] = expected
    stats["complete"] = stats["loans"] == expected
    return stats
