"""Build trustee remittance and correction files for this scenario.

    python data/generate.py
"""
from __future__ import annotations

import csv
import random
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEED = 4242
DEALS = ["SEMT-2023-4", "JPMMT-2024-2", "GCAT-2023-NQM3", "COLT-2024-1", "OBX-2024-NQM5"]
PERIODS = [f"{y}-{m:02d}" for y in (2024, 2025, 2026) for m in range(1, 13)
           if (2024, 7) <= (y, m) <= (2026, 2)]
FIELDS = ["deal_id", "pool_id", "period", "loan_count", "ending_balance", "scheduled_principal",
          "curtailments", "payoffs", "liquidated_balance", "realized_loss", "wac", "wala"]
CORRECTED_PERIOD = "2026-01"
CORRECTION_SENT = "20260218"


def simulate_pool(rng: random.Random, deal: str, group: int) -> list[dict]:
    balance = rng.uniform(80e6, 420e6)
    loans = int(balance / rng.uniform(380_000, 720_000))
    wac = rng.choice([3.25, 3.875, 4.5, 5.125, 6.25, 6.875, 7.4])
    wala = rng.randint(4, 30)
    speed = rng.uniform(0.004, 0.012)  # base SMM
    rows = []
    for period in PERIODS:
        sched = round(balance * rng.uniform(0.0015, 0.0028), 2)
        smm = max(0.0, rng.gauss(speed, speed * 0.35))
        prepay = (balance - sched) * smm
        payoffs = round(prepay * rng.uniform(0.80, 0.95), 2)
        curtail = round(prepay - payoffs, 2)
        liq = round((balance - sched) * max(0.0, rng.gauss(0.0006, 0.0005)), 2) if rng.random() < 0.45 else 0.0
        loss = round(liq * rng.uniform(0.15, 0.45), 2) if liq else 0.0
        ending = round(balance - sched - payoffs - curtail - liq, 2)
        paid_loans = int(round(payoffs / max(balance / max(loans, 1), 1)))
        loans = max(1, loans - paid_loans - (1 if liq else 0))
        wala += 1
        rows.append({"deal_id": deal, "pool_id": f"{deal}-G{group}", "period": period, "loan_count": loans,
                     "ending_balance": ending, "scheduled_principal": sched, "curtailments": curtail,
                     "payoffs": payoffs, "liquidated_balance": liq, "realized_loss": loss,
                     "wac": wac, "wala": wala})
        balance = ending
    return rows


def write(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.2f}" if isinstance(v, float) and k not in ("wac",) else v) for k, v in r.items()})


def main() -> None:
    rng = random.Random(SEED)
    for sub in ("remits", "corrections", "output"):
        if (HERE / sub).exists():
            shutil.rmtree(HERE / sub)
        (HERE / sub).mkdir(parents=True)
    pools = []
    for deal in DEALS:
        for g in range(1, rng.randint(3, 7) + 1):
            pools.append(simulate_pool(rng, deal, g))

    corrected = rng.sample(range(len(pools)), k=7)
    idx = PERIODS.index(CORRECTED_PERIOD)
    first_sent: dict[str, dict] = {}   # pool_id -> January row as the trustee first sent it
    corrections = []
    for i in corrected:
        rows = pools[i]
        r = rows[idx]
        first_sent[r["pool_id"]] = dict(r)
        # The servicer reported a payoff late: it belongs in January, and the
        # lower balance carries into February (February was already right).
        extra = round(r["ending_balance"] * rng.uniform(0.004, 0.012), 2)
        r["payoffs"] = round(r["payoffs"] + extra, 2)
        r["ending_balance"] = round(r["ending_balance"] - extra, 2)
        nxt = rows[idx + 1]
        nxt["ending_balance"] = round(nxt["ending_balance"] - extra, 2)
        corrections.append(dict(r))

    for deal in DEALS:
        for period in PERIODS:
            rows = [p[PERIODS.index(period)] for p in pools if p[0]["deal_id"] == deal]
            if period == CORRECTED_PERIOD:
                rows = [first_sent.get(r["pool_id"], r) for r in rows]
            write(HERE / "remits" / f"{deal}_{period.replace('-', '')}.csv", rows)
    write(HERE / "corrections" / f"correction_{CORRECTED_PERIOD.replace('-', '')}_{CORRECTION_SENT}.csv",
          corrections)
    print(f"{len(pools)} pools, {len(PERIODS)} periods, {len(corrections)} corrections written to {HERE}")


if __name__ == "__main__":
    main()
