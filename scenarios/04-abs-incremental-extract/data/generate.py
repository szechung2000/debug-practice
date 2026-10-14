"""Build the servicer replica and the warehouse state for this scenario.

Timeline:
  1. Loans and their March-April activity are written to the replica.
  2. The extract job runs (initial load) -> warehouse is current to 30 April.
  3. 1 May: the month-end delinquency roll and the day's payments hit the replica.
Afterwards you run the nightly job yourself:
    PYTHONPATH=src python -m abs_cdc.cli run
    PYTHONPATH=src python -m abs_cdc.cli recon
"""
from __future__ import annotations

import os
import random
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = HERE / "source.db"
WAREHOUSE = HERE / "warehouse.db"
SEED = 501
N_LOANS = 38_000
ROLL_TS = "2026-05-01 02:00:00"   # month-end delinquency roll (bulk job)
DEALS = ["SDART-2025-3", "AMCAR-2025-2", "CARMX-2025-4", "DRIVE-2026-1", "ALLYA-2025-5"]
STATES = ["TX", "CA", "FL", "GA", "OH", "NC", "PA", "IL", "AZ", "NY", "MI", "TN"]

DDL = """
CREATE TABLE loans (
    loan_id TEXT PRIMARY KEY, deal_id TEXT NOT NULL, borrower_state TEXT,
    original_balance_cents INTEGER NOT NULL, current_balance_cents INTEGER NOT NULL,
    apr_bps INTEGER NOT NULL, original_term INTEGER NOT NULL, remaining_term INTEGER NOT NULL,
    next_due_date TEXT, days_past_due INTEGER NOT NULL, status TEXT NOT NULL,
    vehicle_type TEXT, ltv_pct REAL, fico INTEGER, updated_at TEXT NOT NULL
);
CREATE INDEX loans_updated_at ON loans (updated_at);
"""


def ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")


def build_source(rng: random.Random) -> None:
    if SOURCE.exists():
        SOURCE.unlink()
    conn = sqlite3.connect(SOURCE)
    conn.executescript(DDL)
    start = datetime(2026, 3, 1, 6, 0, 0)
    rows = []
    for i in range(N_LOANS):
        orig = rng.randint(12_000, 68_000) * 100
        term = rng.choice([48, 60, 72, 72, 75, 84])
        paid = rng.randint(3, 30)
        bal = int(orig * (1 - paid / term) * rng.uniform(0.95, 1.02))
        dpd = rng.choices([0, 0, 0, 0, 0, 0, 0, 12, 35, 64, 95, 130], k=1)[0]
        status = "DELINQUENT" if dpd > 0 else "CURRENT"
        if rng.random() < 0.006:
            status, bal, dpd = "PAID_OFF", 0, 0
        when = start + timedelta(seconds=rng.uniform(0, 60 * 86400))
        rows.append((f"AL{i:07d}", rng.choice(DEALS), rng.choice(STATES), orig, bal,
                     rng.choice([599, 799, 1099, 1449, 1899, 2299]), term, term - paid,
                     "2026-05-15", dpd, status, rng.choice(["NEW", "USED", "USED", "CPO"]),
                     round(rng.uniform(70, 135), 1), rng.randint(540, 820), ts(when)))
    conn.executemany("INSERT INTO loans VALUES (" + ",".join("?" * 15) + ")", rows)
    conn.commit()
    conn.close()


def initial_load() -> None:
    if WAREHOUSE.exists():
        WAREHOUSE.unlink()
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "ABS_SOURCE_DB": str(SOURCE),
           "ABS_WAREHOUSE_DB": str(WAREHOUSE)}
    subprocess.run([sys.executable, "-m", "abs_cdc.cli", "run", "--log-level", "WARNING"],
                   cwd=ROOT, env=env, check=True)


def may_first(rng: random.Random) -> tuple[int, int]:
    conn = sqlite3.connect(SOURCE)
    open_loans = [r[0] for r in conn.execute(
        "SELECT loan_id FROM loans WHERE status IN ('CURRENT', 'DELINQUENT') ORDER BY loan_id")]
    # The month-end roll touches every loan that missed its April payment.
    rolled = rng.sample(open_loans, k=5_620)
    for loan_id in rolled:
        dpd = conn.execute("SELECT days_past_due FROM loans WHERE loan_id = ?", (loan_id,)).fetchone()[0]
        new_dpd = dpd + 30 if dpd else rng.choice([1, 5, 12])
        status = "REPO" if new_dpd >= 150 and rng.random() < 0.3 else "DELINQUENT"
        conn.execute("UPDATE loans SET days_past_due = ?, status = ?, updated_at = ? WHERE loan_id = ?",
                     (new_dpd, status, ROLL_TS, loan_id))
    # Daytime payments, posted one by one by the payment engine.
    others = sorted(set(open_loans) - set(rolled))
    paying = rng.sample(others, k=2_400)
    t = datetime(2026, 5, 1, 7, 30, 0)
    for loan_id in paying:
        t += timedelta(seconds=rng.uniform(0.5, 14.0))
        pay = rng.randint(250, 900) * 100
        conn.execute("UPDATE loans SET current_balance_cents = MAX(current_balance_cents - ?, 0), "
                     "days_past_due = 0, status = 'CURRENT', remaining_term = remaining_term - 1, "
                     "next_due_date = '2026-06-15', updated_at = ? WHERE loan_id = ?", (pay, ts(t), loan_id))
    conn.commit()
    conn.close()
    return len(rolled), len(paying)


def main() -> None:
    rng = random.Random(SEED)
    build_source(rng)
    initial_load()
    rolled, paid = may_first(rng)
    print(f"replica: {N_LOANS} loans; warehouse loaded to 30 April; "
          f"1 May activity: {rolled} roll updates, {paid} payments (not extracted yet)")


if __name__ == "__main__":
    main()
