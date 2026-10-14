"""Build the input files for this scenario (production-sized by default).

    python data/generate.py            # 22 deals, the size of the current book
    python data/generate.py --small    # 3 deals, for quick experiments
"""
from __future__ import annotations

import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEED = 3101
INDUSTRIES = ["Healthcare", "Software", "Business Services", "Chemicals", "Telecom", "Retail",
              "Media", "Aerospace", "Building Products", "Insurance", "Leisure", "Food & Beverage",
              "Hotels", "Electronics", "Transportation", "Utilities", "Containers", "Automotive"]
MOODYS = ["Ba1", "Ba2", "Ba3", "B1", "B2", "B3", "Caa1", "Caa2", "Caa3"]
SP = ["BB+", "BB", "BB-", "B+", "B", "B-", "CCC+", "CCC", "CCC-"]
BASE_WEIGHTS = [6, 10, 18, 32, 28, 4, 1, 1, 0]


def daterange_pick(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def build(out: Path, n_deals: int, positions_per_deal: tuple[int, int]) -> None:
    rng = random.Random(SEED)
    out.mkdir(parents=True, exist_ok=True)
    n_obligors = max(150, n_deals * 70)
    obligors = []
    for i in range(n_obligors):
        facilities = [f"LX{i:05d}{chr(65 + k)}" for k in range(rng.choice([1, 1, 1, 2, 2, 3]))]
        obligors.append({"id": f"OB{i:05d}", "name": f"Obligor {i:05d} Holdings LLC",
                         "industry": rng.choice(INDUSTRIES), "facilities": facilities})

    with (out / "ratings_history.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["loanx_id", "agency", "rating", "as_of"])
        for ob in obligors:
            base = rng.choices(range(len(MOODYS)), weights=BASE_WEIGHTS)[0]
            for lx in ob["facilities"]:
                for agency, scale in (("MOODYS", MOODYS), ("SP", SP)):
                    if rng.random() < 0.05:
                        continue  # not rated by this agency
                    days = sorted(rng.sample(range(0, 1270), k=rng.randint(2, 7)))
                    idx = base
                    for d in days:
                        idx = max(0, min(len(scale) - 1, idx + rng.choice([-1, 0, 0, 0, 0, 0, 0, 0, 1])))
                        rating = scale[idx]
                        if rng.random() < 0.02:
                            rating = "WR"
                        w.writerow([lx, agency, rating, (date(2023, 1, 1) + timedelta(days=d)).isoformat()])

    with (out / "holdings.csv").open("w", newline="") as fh, (out / "deals.csv").open("w", newline="") as dfh:
        w = csv.writer(fh)
        w.writerow(["deal_id", "position_id", "loanx_id", "obligor_id", "obligor_name", "industry",
                    "par", "price", "spread_bps", "is_defaulted", "settle_date"])
        dw = csv.writer(dfh)
        dw.writerow(["deal_id", "senior_notes", "oc_trigger"])
        pos_no = 0
        for d in range(n_deals):
            deal_id = f"CLO-{2019 + d % 7}-{d + 1:02d}"
            picks = rng.sample(obligors, k=rng.randint(*positions_per_deal))
            deal_par = 0.0
            for ob in picks:
                for lx in rng.sample(ob["facilities"], k=rng.randint(1, len(ob["facilities"]))):
                    pos_no += 1
                    par = round(rng.uniform(250_000, 4_750_000), 2)
                    defaulted = int(rng.random() < 0.012)
                    price = round(rng.uniform(18, 55) if defaulted else rng.uniform(72, 100.5), 3)
                    settle = daterange_pick(rng, date(2021, 6, 1), date(2026, 4, 20))
                    w.writerow([deal_id, f"P{pos_no:07d}", lx, ob["id"], ob["name"], ob["industry"], par,
                                price, rng.choice([300, 325, 350, 375, 400, 425, 450, 500]), defaulted,
                                settle.isoformat()])
                    deal_par += par
            dw.writerow([deal_id, round(deal_par * rng.uniform(0.74, 0.80), 2), rng.choice([118.0, 120.5, 122.0])])
    print(f"inputs written to {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--small", action="store_true")
    ap.add_argument("--out", type=Path, default=HERE / "input")
    args = ap.parse_args()
    if args.small:
        build(args.out, 3, (120, 160))
    else:
        build(args.out, 22, (330, 420))


if __name__ == "__main__":
    main()
