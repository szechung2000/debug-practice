import sqlite3
from contextlib import closing
from dataclasses import replace

import pytest

from abs_cdc import cli, recon, transform, warehouse
from abs_cdc.config import ExtractConfig

DDL = """
CREATE TABLE loans (
    loan_id TEXT PRIMARY KEY, deal_id TEXT NOT NULL, borrower_state TEXT,
    original_balance_cents INTEGER NOT NULL, current_balance_cents INTEGER NOT NULL,
    apr_bps INTEGER NOT NULL, original_term INTEGER NOT NULL, remaining_term INTEGER NOT NULL,
    next_due_date TEXT, days_past_due INTEGER NOT NULL, status TEXT NOT NULL,
    vehicle_type TEXT, ltv_pct REAL, fico INTEGER, updated_at TEXT NOT NULL
);
"""


def raw(loan_id="L1", dpd=0, status="CURRENT", ts="2026-05-01 07:00:00.000001"):
    return {"loan_id": loan_id, "deal_id": "D", "borrower_state": "TX", "original_balance_cents": 2_000_000,
            "current_balance_cents": 1_234_567, "apr_bps": 1099, "original_term": 72, "remaining_term": 60,
            "next_due_date": "2026-05-15", "days_past_due": dpd, "status": status, "vehicle_type": "USED",
            "ltv_pct": 101.5, "fico": 701, "updated_at": ts}


@pytest.mark.parametrize("dpd,status,bucket", [
    (0, "CURRENT", "CURRENT"), (12, "DELINQUENT", "1-29"), (30, "DELINQUENT", "30-59"),
    (95, "DELINQUENT", "90-119"), (130, "DELINQUENT", "120+"), (0, "PAID_OFF", "PAID_OFF"), (160, "REPO", "REPO"),
])
def test_dq_bucket(dpd, status, bucket):
    assert transform.dq_bucket(dpd, status) == bucket


def test_to_warehouse_amounts():
    row = transform.to_warehouse(raw())
    assert row["current_balance"] == "12345.67"
    assert row["apr"] == "0.1099"


def test_bad_status_rejected():
    result = transform.transform_page([raw(status="??")])
    assert not result.rows and len(result.rejected) == 1


def test_older_row_does_not_overwrite_newer(tmp_path):
    with closing(warehouse.connect(tmp_path / "w.db")) as conn:
        with conn:
            warehouse.merge_rows(conn, [transform.to_warehouse(raw(dpd=30, status="DELINQUENT",
                                                                   ts="2026-05-02 00:00:00"))], "r1")
            warehouse.merge_rows(conn, [transform.to_warehouse(raw(ts="2026-05-01 00:00:00"))], "r2")
        assert conn.execute("SELECT dq_bucket FROM auto_loan_current").fetchone()[0] == "30-59"


def test_incremental_picks_up_new_changes(tmp_path):
    src = tmp_path / "s.db"
    with closing(sqlite3.connect(src)) as conn:
        conn.executescript(DDL)
        for i in range(25):
            r = raw(f"L{i:03d}", ts=f"2026-05-01 07:00:{i:02d}.5")
            conn.execute("INSERT INTO loans VALUES (" + ",".join("?" * 15) + ")", tuple(r.values()))
        conn.commit()
    cfg = replace(ExtractConfig.from_env(str(src), str(tmp_path / "w.db")), page_size=10)
    assert cli.run_incremental(cfg)["read"] == 25
    with closing(sqlite3.connect(src)) as conn:
        conn.execute("UPDATE loans SET days_past_due = 5, status = 'DELINQUENT', "
                     "updated_at = '2026-05-02 08:00:00.1' WHERE loan_id = 'L003'")
        conn.commit()
    assert cli.run_incremental(cfg)["read"] >= 1
    assert cli.run_recon(cfg) == 0
    with closing(sqlite3.connect(tmp_path / "w.db")) as conn:
        assert conn.execute("SELECT dq_bucket FROM auto_loan_current WHERE loan_id = 'L003'").fetchone()[0] == "1-29"


def test_recon_detects_missing_loan():
    diffs = recon.reconcile([("CURRENT", 0, 2, 200)], [("CURRENT", 0, 1, 100)])
    assert not diffs[0].ok
