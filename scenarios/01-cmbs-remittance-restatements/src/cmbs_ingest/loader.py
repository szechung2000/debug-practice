"""Load current loan periodic rows into the warehouse (SQLite stands in for prod)."""
from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from pathlib import Path

log = logging.getLogger(__name__)

DDL = """
CREATE TABLE IF NOT EXISTS loan_periodic (
    deal_id               TEXT NOT NULL,
    loan_id               TEXT NOT NULL,
    period                TEXT NOT NULL,
    distribution_date     TEXT NOT NULL,
    determination_date    TEXT NOT NULL,
    beginning_balance     TEXT NOT NULL,
    scheduled_principal   TEXT NOT NULL,
    unscheduled_principal TEXT NOT NULL,
    total_principal       TEXT NOT NULL,
    ending_balance        TEXT NOT NULL,
    current_rate          TEXT NOT NULL,
    paid_through_date     TEXT,
    delinquency_status    TEXT NOT NULL,
    dq_bucket             TEXT NOT NULL,
    is_paid_off           INTEGER NOT NULL,
    servicer              TEXT NOT NULL,
    source_file           TEXT NOT NULL,
    received_at           TEXT NOT NULL,
    loaded_at             TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (deal_id, loan_id, period)
);
CREATE TABLE IF NOT EXISTS load_audit (
    run_id     TEXT NOT NULL,
    deal_id    TEXT NOT NULL,
    period     TEXT NOT NULL,
    row_count  INTEGER NOT NULL,
    loaded_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

COLUMNS = (
    "deal_id", "loan_id", "period", "distribution_date", "determination_date",
    "beginning_balance", "scheduled_principal", "unscheduled_principal", "total_principal",
    "ending_balance", "current_rate", "paid_through_date", "delinquency_status", "dq_bucket",
    "is_paid_off", "servicer", "source_file", "received_at",
)


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(DDL)
    return conn


def upsert(conn: sqlite3.Connection, rows: list[dict], run_id: str) -> int:
    """Replace each (deal, period) partition that appears in `rows`.

    The job owns whole partitions: a rerun deletes the partition and writes
    it again, so a loan that left the deal does not linger.
    """
    partitions = sorted({(r["deal_id"], r["period"]) for r in rows})
    placeholders = ", ".join("?" for _ in COLUMNS)
    sql = f"INSERT INTO loan_periodic ({', '.join(COLUMNS)}) VALUES ({placeholders})"
    with conn:
        for deal_id, period in partitions:
            conn.execute("DELETE FROM loan_periodic WHERE deal_id = ? AND period = ?", (deal_id, period))
        conn.executemany(sql, [tuple(r[c] for c in COLUMNS) for r in rows])
        counts: dict[tuple[str, str], int] = {}
        for r in rows:
            counts[(r["deal_id"], r["period"])] = counts.get((r["deal_id"], r["period"]), 0) + 1
        conn.executemany(
            "INSERT INTO load_audit (run_id, deal_id, period, row_count) VALUES (?, ?, ?, ?)",
            [(run_id, d, p, n) for (d, p), n in counts.items()],
        )
    log.info("loaded %d rows into %d partitions", len(rows), len(partitions))
    return len(rows)


def read_partition(path: Path, deal_id: str, period: str) -> list[dict]:
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT * FROM loan_periodic WHERE deal_id = ? AND period = ? ORDER BY loan_id", (deal_id, period))
        return [dict(r) for r in cur.fetchall()]
