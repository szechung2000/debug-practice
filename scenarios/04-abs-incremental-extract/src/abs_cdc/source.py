"""Read changed loans from the servicer's replica.

The replica exposes one table, `loans`, with an `updated_at` column that the
servicing platform sets on every write (UTC, text, 'YYYY-MM-DD HH:MM:SS[.ffffff]').
We pull changes in pages so one extract never holds a long read transaction
on the replica.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

SOURCE_COLUMNS = (
    "loan_id", "deal_id", "borrower_state", "original_balance_cents", "current_balance_cents",
    "apr_bps", "original_term", "remaining_term", "next_due_date", "days_past_due", "status",
    "vehicle_type", "ltv_pct", "fico", "updated_at",
)
EPOCH = "1970-01-01 00:00:00"


class SourceError(Exception):
    pass


@dataclass(frozen=True)
class Page:
    rows: list[dict]
    last_updated_at: str

    def __len__(self) -> int:
        return len(self.rows)


class SourceClient:
    def __init__(self, path: Path, max_retries: int = 3, backoff_s: float = 0.5):
        if not path.exists():
            raise SourceError(f"source replica not found: {path}")
        self.path = path
        self.max_retries = max_retries
        self.backoff_s = backoff_s

    def _query(self, sql: str, params: tuple) -> list[sqlite3.Row]:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=10)
                try:
                    conn.row_factory = sqlite3.Row
                    return conn.execute(sql, params).fetchall()
                finally:
                    conn.close()
            except sqlite3.OperationalError as exc:  # replica lag / lock
                last_exc = exc
                log.warning("source query failed (attempt %d/%d): %s", attempt, self.max_retries, exc)
                time.sleep(self.backoff_s * attempt)
        raise SourceError(f"source query failed after {self.max_retries} attempts") from last_exc

    def fetch_page(self, since: str, limit: int) -> Page:
        sql = (f"SELECT {', '.join(SOURCE_COLUMNS)} FROM loans "
               f"WHERE updated_at > ? ORDER BY updated_at LIMIT ?")
        rows = [dict(r) for r in self._query(sql, (since, limit))]
        return Page(rows, rows[-1]["updated_at"] if rows else since)

    def iter_changes(self, since: str | None, page_size: int, max_pages: int) -> Iterator[Page]:
        cursor = since or EPOCH
        for page_no in range(1, max_pages + 1):
            page = self.fetch_page(cursor, page_size)
            if not page.rows:
                return
            log.debug("page %d: %d rows, %s .. %s", page_no, len(page),
                      page.rows[0]["updated_at"], page.last_updated_at)
            yield page
            if len(page) < page_size:
                return
            cursor = page.last_updated_at
        raise SourceError(f"extract did not finish within {max_pages} pages")

    def snapshot_counts(self) -> list[sqlite3.Row]:
        """Counts and balances by status, used by the reconciliation."""
        return self._query(
            "SELECT status, days_past_due, COUNT(*) AS n, SUM(current_balance_cents) AS bal "
            "FROM loans GROUP BY status, days_past_due", ())
