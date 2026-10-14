"""Warehouse side: current-state table, status history, job state."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

DDL = """
CREATE TABLE IF NOT EXISTS auto_loan_current (
    loan_id           TEXT PRIMARY KEY,
    deal_id           TEXT NOT NULL,
    borrower_state    TEXT,
    original_balance  TEXT NOT NULL,
    current_balance   TEXT NOT NULL,
    apr               TEXT NOT NULL,
    original_term     INTEGER NOT NULL,
    remaining_term    INTEGER NOT NULL,
    next_due_date     TEXT,
    days_past_due     INTEGER NOT NULL,
    dq_bucket         TEXT NOT NULL,
    status            TEXT NOT NULL,
    vehicle_type      TEXT,
    ltv_pct           REAL,
    fico              INTEGER,
    source_updated_at TEXT NOT NULL,
    loaded_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now'))
);
CREATE TABLE IF NOT EXISTS loan_status_history (
    loan_id      TEXT NOT NULL,
    status       TEXT NOT NULL,
    dq_bucket    TEXT NOT NULL,
    effective_at TEXT NOT NULL,
    run_id       TEXT NOT NULL,
    PRIMARY KEY (loan_id, effective_at)
);
CREATE TABLE IF NOT EXISTS etl_state (
    job        TEXT PRIMARY KEY,
    watermark  TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS etl_runs (
    run_id      TEXT PRIMARY KEY,
    job         TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    watermark_from TEXT,
    watermark_to   TEXT,
    rows_read   INTEGER,
    rows_merged INTEGER,
    rows_rejected INTEGER,
    status      TEXT NOT NULL
);
"""

CURRENT_COLUMNS = (
    "loan_id", "deal_id", "borrower_state", "original_balance", "current_balance", "apr",
    "original_term", "remaining_term", "next_due_date", "days_past_due", "dq_bucket", "status",
    "vehicle_type", "ltv_pct", "fico", "source_updated_at",
)


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(DDL)
    return conn


def get_watermark(conn: sqlite3.Connection, job: str) -> str | None:
    row = conn.execute("SELECT watermark FROM etl_state WHERE job = ?", (job,)).fetchone()
    return row[0] if row else None


def set_watermark(conn: sqlite3.Connection, job: str, watermark: str) -> None:
    conn.execute(
        "INSERT INTO etl_state (job, watermark) VALUES (?, ?) "
        "ON CONFLICT(job) DO UPDATE SET watermark = excluded.watermark, updated_at = datetime('now')",
        (job, watermark))


def merge_rows(conn: sqlite3.Connection, rows: list[dict], run_id: str) -> int:
    """Upsert current state; append a history row when status or bucket changes.

    A row only replaces the stored row if it is newer, so replaying a page is
    harmless.
    """
    if not rows:
        return 0
    cols = ", ".join(CURRENT_COLUMNS)
    marks = ", ".join("?" for _ in CURRENT_COLUMNS)
    updates = ", ".join(f"{c} = excluded.{c}" for c in CURRENT_COLUMNS if c != "loan_id")
    ids = [r["loan_id"] for r in rows]
    prior = {}
    for i in range(0, len(ids), 900):
        chunk = ids[i:i + 900]
        q = f"SELECT loan_id, status, dq_bucket FROM auto_loan_current WHERE loan_id IN ({','.join('?' * len(chunk))})"
        prior.update({r[0]: (r[1], r[2]) for r in conn.execute(q, chunk)})
    conn.executemany(
        f"INSERT INTO auto_loan_current ({cols}) VALUES ({marks}) "
        f"ON CONFLICT(loan_id) DO UPDATE SET {updates}, loaded_at = strftime('%Y-%m-%d %H:%M:%f', 'now') "
        f"WHERE excluded.source_updated_at >= auto_loan_current.source_updated_at",
        [tuple(r[c] for c in CURRENT_COLUMNS) for r in rows])
    history = [(r["loan_id"], r["status"], r["dq_bucket"], r["source_updated_at"], run_id)
               for r in rows if prior.get(r["loan_id"]) != (r["status"], r["dq_bucket"])]
    conn.executemany("INSERT OR IGNORE INTO loan_status_history VALUES (?, ?, ?, ?, ?)", history)
    return len(rows)


def warehouse_counts(conn: sqlite3.Connection) -> list[tuple]:
    return conn.execute(
        "SELECT status, days_past_due, COUNT(*), SUM(CAST(ROUND(CAST(current_balance AS REAL) * 100) AS INTEGER)) "
        "FROM auto_loan_current GROUP BY status, days_past_due").fetchall()
