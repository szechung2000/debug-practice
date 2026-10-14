"""Entry points:
    python -m abs_cdc.cli run      # incremental extract and merge
    python -m abs_cdc.cli recon    # compare the warehouse with the replica
    python -m abs_cdc.cli status   # show the watermark and the last runs
"""
from __future__ import annotations

import argparse
import logging
import sys
import uuid
from contextlib import closing
from datetime import datetime, timezone

from . import recon, transform, warehouse
from .config import JOB_NAME, ExtractConfig, configure_logging
from .source import SourceClient, SourceError

log = logging.getLogger("abs_cdc")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def run_incremental(cfg: ExtractConfig) -> dict:
    run_id = uuid.uuid4().hex[:12]
    source = SourceClient(cfg.source_path, cfg.max_retries, cfg.retry_backoff_s)
    stats = {"run_id": run_id, "read": 0, "merged": 0, "rejected": 0, "pages": 0}
    with closing(warehouse.connect(cfg.warehouse_path)) as conn:
        start_wm = warehouse.get_watermark(conn, JOB_NAME)
        with conn:
            conn.execute("INSERT INTO etl_runs (run_id, job, started_at, watermark_from, status) "
                         "VALUES (?, ?, ?, ?, 'RUNNING')", (run_id, JOB_NAME, now(), start_wm))
        log.info("run %s: extracting changes after %s (page size %d)",
                 run_id, start_wm or "the beginning", cfg.page_size)
        wm = start_wm
        try:
            for page in source.iter_changes(start_wm, cfg.page_size, cfg.max_pages):
                result = transform.transform_page(page.rows)
                # One transaction per page: merge rows and move the watermark
                # together, so a crash never skips or loses a page.
                with conn:
                    stats["merged"] += warehouse.merge_rows(conn, result.rows, run_id)
                    warehouse.set_watermark(conn, JOB_NAME, page.last_updated_at)
                wm = page.last_updated_at
                stats["pages"] += 1
                stats["read"] += len(page)
                stats["rejected"] += len(result.rejected)
        except SourceError:
            with conn:
                conn.execute("UPDATE etl_runs SET status='FAILED', finished_at=?, watermark_to=? WHERE run_id=?",
                             (now(), wm, run_id))
            raise
        with conn:
            conn.execute(
                "UPDATE etl_runs SET status='OK', finished_at=?, watermark_to=?, rows_read=?, rows_merged=?, "
                "rows_rejected=? WHERE run_id=?",
                (now(), wm, stats["read"], stats["merged"], stats["rejected"], run_id))
    log.info("run %s: %d pages, %d rows read, %d merged, %d rejected, watermark %s -> %s",
             run_id, stats["pages"], stats["read"], stats["merged"], stats["rejected"], start_wm, wm)
    return stats


def run_recon(cfg: ExtractConfig) -> int:
    source = SourceClient(cfg.source_path, cfg.max_retries, cfg.retry_backoff_s)
    with closing(warehouse.connect(cfg.warehouse_path)) as conn:
        diffs = recon.reconcile(source.snapshot_counts(), warehouse.warehouse_counts(conn))
    breaks = recon.log_report(diffs)
    log.info("recon: %d buckets, %d breaks", len(diffs), breaks)
    return breaks


def show_status(cfg: ExtractConfig) -> None:
    with closing(warehouse.connect(cfg.warehouse_path)) as conn:
        print("watermark:", warehouse.get_watermark(conn, JOB_NAME))
        for row in conn.execute("SELECT run_id, started_at, watermark_from, watermark_to, rows_read, status "
                                "FROM etl_runs ORDER BY started_at DESC LIMIT 10"):
            print(" ", row)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="abs_cdc")
    ap.add_argument("cmd", choices=["run", "recon", "status"])
    ap.add_argument("--source")
    ap.add_argument("--warehouse")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    configure_logging(args.log_level)
    cfg = ExtractConfig.from_env(args.source, args.warehouse)
    try:
        if args.cmd == "run":
            run_incremental(cfg)
        elif args.cmd == "recon":
            return 1 if run_recon(cfg) else 0
        else:
            show_status(cfg)
    except SourceError as exc:
        log.error("%s", exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
