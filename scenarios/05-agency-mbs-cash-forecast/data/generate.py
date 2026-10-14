"""Build positions, agency factors and the Federal Reserve holiday calendar.

    python data/generate.py
"""
from __future__ import annotations

import csv
import random
import sys
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
from mbs_cash.inputs import cusip_check_digit  # noqa: E402

OUT = HERE / "input"
SEED = 1225
ACCOUNTS = ["TSY-LIQ-01", "TSY-LIQ-02", "ALM-CORE", "INS-GA-03"]
PROGRAM_PREFIX = {"UMBS": ["3140", "3138"], "FHLMC_GOLD": ["3128", "3132"], "GNMA_I": ["3620"],
                  "GNMA_II": ["3617", "3622"]}
COUPONS = ["2.0", "2.5", "3.0", "3.5", "4.0", "4.5", "5.0", "5.5", "6.0", "6.5"]
PERIODS = [f"2026-{m:02d}" for m in range(6, 13)]
FED_HOLIDAYS = [
    ("2026-01-01", "New Year's Day"), ("2026-01-19", "Birthday of Martin Luther King, Jr."),
    ("2026-02-16", "Washington's Birthday"), ("2026-05-25", "Memorial Day"),
    ("2026-06-19", "Juneteenth National Independence Day"), ("2026-07-03", "Independence Day (observed)"),
    ("2026-09-07", "Labor Day"), ("2026-10-12", "Columbus Day"), ("2026-11-11", "Veterans Day"),
    ("2026-11-26", "Thanksgiving Day"), ("2026-12-25", "Christmas Day"),
    ("2027-01-01", "New Year's Day"), ("2027-01-18", "Birthday of Martin Luther King, Jr."),
    ("2027-02-15", "Washington's Birthday"), ("2027-05-31", "Memorial Day"),
    ("2027-07-05", "Independence Day (observed)"), ("2027-09-06", "Labor Day"),
    ("2027-10-11", "Columbus Day"), ("2027-11-11", "Veterans Day"), ("2027-11-25", "Thanksgiving Day"),
]


def make_cusip(rng: random.Random, program: str) -> str:
    alnum = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    base = rng.choice(PROGRAM_PREFIX[program]) + "".join(rng.choice(alnum) for _ in range(4))
    return base + str(cusip_check_digit(base))


def main() -> None:
    rng = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "fed_holidays.csv").open("w", newline="") as fh:
        fh.write("# Federal Reserve Bank holidays (Fedwire closed). Source: federalreserve.gov\n")
        fh.write("# When a holiday falls on a Saturday, Reserve Banks are open the preceding Friday.\n")
        w = csv.writer(fh)
        w.writerow(["date", "name"])
        w.writerows(FED_HOLIDAYS)

    pools = []
    seen = set()
    for program, n in (("UMBS", 120), ("FHLMC_GOLD", 25), ("GNMA_I", 30), ("GNMA_II", 70)):
        for _ in range(n):
            cusip = make_cusip(rng, program)
            while cusip in seen:
                cusip = make_cusip(rng, program)
            seen.add(cusip)
            prefix = "MA" if program == "UMBS" else ("G0" if program == "FHLMC_GOLD" else "")
            pools.append({"cusip": cusip, "program": program, "pool_number": f"{prefix}{rng.randint(1000, 9999)}",
                          "coupon": rng.choice(COUPONS), "factor": Decimal(str(round(rng.uniform(0.18, 0.97), 8)))})

    with (OUT / "factors.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["cusip", "period", "factor"])
        for p in pools:
            f = p["factor"]
            for period in PERIODS:
                w.writerow([p["cusip"], period, f"{f:.8f}"])
                f = (f * Decimal(str(1 - rng.uniform(0.003, 0.012)))).quantize(Decimal("0.00000001"))

    with (OUT / "positions.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["account", "cusip", "pool_number", "program", "coupon", "original_face"])
        for p in pools:
            for account in rng.sample(ACCOUNTS, k=rng.choice([1, 1, 2])):
                face = rng.randint(2, 120) * 250_000
                w.writerow([account, p["cusip"], p["pool_number"], p["program"], p["coupon"], f"{face:,}"])
    print(f"{len(pools)} pools written to {OUT}")


if __name__ == "__main__":
    main()
