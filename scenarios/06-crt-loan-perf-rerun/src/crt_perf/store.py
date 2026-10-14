"""Loan performance store (SQLite stands in for the warehouse).

Partitions are (deal_id, reporting_period). The load job owns a whole
partition: a run replaces the partition, so a rerun is safe.
"""
from __future__ import annotations

import logging
import sqlite3
from decimal import Decimal
from pathlib import Path

log = logging.getLogger(__name__)

DDL = """
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS loan_performance (
    deal_id TEXT NOT NULL, loan_id TEXT NOT NULL, reporting_period TEXT NOT NULL,
    current_upb TEXT NOT NULL, current_rate TEXT, loan_age INTEGER, remaining_months INTEGER,
    dq_status TEXT NOT NULL, dq_bucket TEXT NOT NULL, is_60_plus INTEGER NOT NULL,
    modification_flag INTEGER NOT NULL, zero_balance_code TEXT, zero_balance_date TEXT,
    event_type TEXT, net_sales_proceeds TEXT, prior_upb TEXT, estimated_loss TEXT, property_state TEXT,
    loaded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now'))
);
CREATE INDEX IF NOT EXISTS lp_partition ON loan_performance (deal_id, reporting_period);
CREATE TABLE IF NOT EXISTS load_runs (
    run_id TEXT PRIMARY KEY, deal_id TEXT NOT NULL, period TEXT NOT NULL, file_name TEXT NOT NULL,
    file_rows INTEGER, loaded_rows INTEGER, chunks_ok INTEGER, chunks_failed INTEGER,
    status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT
);
"""
INSERT_SQL = ("INSERT INTO loan_performance (deal_id, loan_id, reporting_period, current_upb, current_rate, "
              "loan_age, remaining_months, dq_status, dq_bucket, is_60_plus, modification_flag, "
              "zero_balance_code, zero_balance_date, event_type, net_sales_proceeds, prior_upb, estimated_loss, "
              "property_state) VALUES (" + ",".join("?" * 18) + ")")


def connect(path: Path, busy_timeout_ms: int = 30_000) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=busy_timeout_ms / 1000)
    conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
    conn.executescript(DDL)
    return conn


def delete_partition(conn: sqlite3.Connection, deal_id: str, period: str) -> int:
    cur = conn.execute("DELETE FROM loan_performance WHERE deal_id = ? AND reporting_period = ?",
                       (deal_id, period))
    return cur.rowcount


def insert_rows(conn: sqlite3.Connection, rows: list[tuple]) -> int:
    conn.executemany(INSERT_SQL, rows)
    return len(rows)


def prior_upbs(conn: sqlite3.Connection, deal_id: str, prior_period_iso: str) -> dict[str, Decimal]:
    cur = conn.execute("SELECT loan_id, current_upb FROM loan_performance WHERE deal_id = ? AND reporting_period = ?",
                       (deal_id, prior_period_iso))
    return {loan_id: Decimal(upb) for loan_id, upb in cur}


def partition_stats(conn: sqlite3.Connection, deal_id: str, period_iso: str) -> dict:
    row = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT loan_id), "
        "SUM(CAST(current_upb AS REAL)), SUM(is_60_plus * CAST(current_upb AS REAL)), "
        "SUM(CASE WHEN event_type = 'CREDIT_EVENT' THEN 1 ELSE 0 END), "
        "SUM(CAST(COALESCE(estimated_loss, '0') AS REAL)) "
        "FROM loan_performance WHERE deal_id = ? AND reporting_period = ?", (deal_id, period_iso)).fetchone()
    rows, loans, upb, upb60, events, loss = row
    return {"rows": rows, "loans": loans, "upb": upb or 0.0, "upb_60_plus": upb60 or 0.0,
            "credit_events": events or 0, "estimated_loss": loss or 0.0,
            "dq60_pct": (100.0 * (upb60 or 0.0) / upb) if upb else 0.0}
