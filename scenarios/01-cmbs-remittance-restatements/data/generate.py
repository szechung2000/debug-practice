"""Build the landing zone for this scenario: servicer files, manifest, trustee totals.

Deterministic: the same seed gives the same files. Run from the scenario folder:
    python data/generate.py
"""
from __future__ import annotations

import csv
import hashlib
import random
import shutil
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
LANDING = HERE / "landing"
SEED = 20260112

DEALS = {
    "BMARK-2024-V9": "MIDLAND",
    "BANK5-2024-5YR8": "WELLS",
    "WFCM-2023-C61": "WELLS",
    "MSC-2024-L4": "KEYBANK",
    "COMM-2022-LC3": "TRIMONT",
    "BBCMS-2025-C32": "PNC",
}
PERIODS = ["202510", "202511", "202512", "202601"]
# (deal, period): (original received_at, restatement received_at)
RESTATEMENTS = {
    ("COMM-2022-LC3", "202510"): ("10/17/2025 08:12:44", "11/04/2025 16:40:02"),
    ("WFCM-2023-C61", "202511"): ("11/18/2025 07:55:10", "12/03/2025 11:21:37"),
    ("BMARK-2024-V9", "202512"): ("12/17/2025 09:03:51", "01/07/2026 14:18:09"),
    ("BANK5-2024-5YR8", "202512"): ("12/18/2025 06:47:33", "01/09/2026 10:02:56"),
    ("MSC-2024-L4", "202601"): ("01/20/2026 08:30:00", "02/06/2026 09:45:12"),
}
CENT = Decimal("0.01")
FIELDS = ["transaction_id", "loan_id", "distribution_date", "determination_date", "beginning_balance",
          "scheduled_principal", "unscheduled_principal", "ending_balance", "current_rate",
          "paid_through_date", "delinquency_status", "servicer_comment"]


def q(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt_amount(x: Decimal, rng: random.Random) -> str:
    style = rng.random()
    if style < 0.7:
        return f"{x:.2f}"
    if style < 0.95:
        return f"{x:,.2f}"
    return f"${x:,.2f}"


def build_loans(rng: random.Random, deal: str) -> list[dict]:
    n = rng.randint(28, 46)
    prefix = deal.split("-")[0][:4]
    return [{
        "loan_id": f"{prefix}{i:04d}",
        "balance": q(Decimal(rng.randint(2_000_000, 95_000_000))),
        "rate": Decimal(rng.choice(["0.0485", "0.0525", "0.0561", "0.0610", "0.0675", "0.0702"])),
        "amort": rng.random() < 0.55,
    } for i in range(1, n + 1)]


def period_rows(rng: random.Random, deal: str, period: str, loans: list[dict]) -> list[dict]:
    year, month = int(period[:4]), int(period[4:])
    det = f"{year}{month:02d}11"
    dist = f"{year}-{month:02d}-17"
    rows = []
    for loan in loans:
        beg = loan["balance"]
        if beg <= 0:
            continue
        sched = q(beg * loan["rate"] / 12 * Decimal("0.18")) if loan["amort"] else Decimal("0.00")
        unsched = Decimal("0.00")
        comment = ""
        if rng.random() < 0.015:
            unsched = beg - sched
            comment = "Loan paid off in full"
        elif rng.random() < 0.04:
            unsched = q(beg * Decimal(rng.choice(["0.01", "0.02", "0.05"])))
            comment = "Partial prepayment"
        end = beg - sched - unsched
        dq = rng.choices(["0", "0", "0", "0", "A", "1", "3"], k=1)[0]
        rows.append({
            "transaction_id": deal, "loan_id": loan["loan_id"], "distribution_date": dist,
            "determination_date": det, "beginning_balance": beg, "scheduled_principal": sched,
            "unscheduled_principal": unsched, "ending_balance": end,
            "current_rate": loan["rate"] if rng.random() < 0.6 else loan["rate"] * 100,
            "paid_through_date": f"{month:02d}/01/{year}", "delinquency_status": dq,
            "servicer_comment": comment,
        })
        loan["balance"] = end
    return rows


def restate(rng: random.Random, rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (rows as restated, the subset the servicer resent)."""
    restated = [dict(r) for r in rows]
    picks = rng.sample(range(len(restated)), k=min(4, len(restated)))
    for i in picks:
        r = restated[i]
        extra = q(r["ending_balance"] * Decimal("0.035"))
        r["unscheduled_principal"] += extra
        r["ending_balance"] -= extra
        r["servicer_comment"] = "Restated: curtailment received after determination date"
    return restated, [restated[i] for i in sorted(picks)]


def write_file(path: Path, rows: list[dict], rng: random.Random) -> None:
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            out = dict(r)
            for k in ("beginning_balance", "scheduled_principal", "unscheduled_principal", "ending_balance"):
                out[k] = fmt_amount(r[k], rng)
            out["current_rate"] = f"{r['current_rate']:.4f}"
            w.writerow(out)


def main() -> None:
    rng = random.Random(SEED)
    if LANDING.exists():
        shutil.rmtree(LANDING)
    LANDING.mkdir(parents=True)
    manifest_rows, trustee_rows = [], []
    for deal, servicer in DEALS.items():
        loans = build_loans(rng, deal)
        for period in PERIODS:
            rows = period_rows(rng, deal, period, loans)
            name = f"{deal}_{period}_LPU.csv"
            write_file(LANDING / name, rows, rng)
            final = rows
            orig_ts, re_ts = RESTATEMENTS.get((deal, period), (None, None))
            day = int(period[4:])
            manifest_rows.append((name, servicer, orig_ts or f"{day:02d}/1{rng.randint(5, 9)}/{period[:4]} "
                                                              f"0{rng.randint(6, 9)}:{rng.randint(10, 59)}:{rng.randint(10, 59)}"))
            if re_ts:
                final, resent = restate(rng, rows)
                re_name = f"{deal}_{period}_LPU_R1.csv"
                write_file(LANDING / re_name, resent, rng)
                manifest_rows.append((re_name, servicer, re_ts))
                # carry restated balances into the next period
                by_id = {r["loan_id"]: r["ending_balance"] for r in final}
                for loan in loans:
                    if loan["loan_id"] in by_id:
                        loan["balance"] = by_id[loan["loan_id"]]
            trustee_rows.append((deal, period, len(final), sum(r["ending_balance"] for r in final)))
    with (LANDING / "manifest.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file_name", "servicer", "received_at", "sha256"])
        for name, servicer, ts in sorted(manifest_rows, key=lambda m: m[0]):
            digest = hashlib.sha256((LANDING / name).read_bytes()).hexdigest()
            w.writerow([name, servicer, ts, digest])
    with (LANDING / "trustee_remittance.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["deal_id", "period", "loan_count", "ending_balance"])
        for deal, period, count, bal in trustee_rows:
            w.writerow([deal, period, count, f"{bal:.2f}"])
    print(f"landing zone written to {LANDING} ({len(manifest_rows)} files)")


if __name__ == "__main__":
    main()
