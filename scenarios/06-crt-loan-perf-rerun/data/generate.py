"""Build vendor files and the store state for this scenario.

Timeline:
  1. July and August files for two deals, loaded cleanly.
  2. September files arrive. CAS-2024-R03's file has one bad record; its load
     fails part way (other chunks commit).
  3. The vendor resends a corrected CAS-2024-R03 September file.
Afterwards you rerun the load yourself:
    PYTHONPATH=src python -m crt_perf.cli load --deal CAS-2024-R03 --period 2026-09
"""
from __future__ import annotations

import os
import random
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
INBOUND = HERE / "inbound"
STORE = HERE / "crt_store.db"
SEED = 906
DEALS = {"CAS-2024-R03": 31_500, "STACR-2025-DNA2": 22_000}
PERIODS = ["2026-07", "2026-08", "2026-09"]
STATES = ["CA", "TX", "FL", "NY", "WA", "CO", "NJ", "IL", "VA", "AZ", "GA", "MA"]


def simulate(rng: random.Random, deal: str, n: int) -> dict[str, list[str]]:
    loans = [{"id": f"{deal[:4]}{i:08d}", "upb": Decimal(rng.randint(120_000, 780_000)),
              "rate": rng.choice(["6.125", "6.500", "6.875", "7.250", "7.625"]), "age": rng.randint(6, 20),
              "dq": rng.choice([0] * 60 + [2, 3, 4, 5, 6]), "state": rng.choice(STATES), "mod": "N", "gone": False} for i in range(n)]
    files: dict[str, list[str]] = {}
    for period in PERIODS:
        lines = []
        mmYYYY = period[5:] + period[:4]
        for ln in loans:
            if ln["gone"]:
                continue
            ln["age"] += 1
            zb, zb_date, nsp, event = "", "", "", "N"
            r = rng.random()
            if r < 0.006:                              # voluntary payoff
                zb, zb_date, ln["upb"], ln["gone"] = "01", mmYYYY, Decimal(0), True
            elif ln["dq"] >= 4 and r < 0.08:           # REO / short sale -> credit event
                zb, zb_date, event, ln["gone"] = rng.choice(["02", "03", "09"]), mmYYYY, "Y", True
                nsp = f"{ln['upb'] * Decimal(rng.uniform(0.55, 0.9)):.2f}"
                ln["upb"] = Decimal(0)
            else:
                ln["upb"] = (ln["upb"] * Decimal("0.9987")).quantize(Decimal("0.01"))
                if ln["dq"]:
                    ln["dq"] = ln["dq"] + 1 if rng.random() < 0.7 else 0
                elif rng.random() < 0.012:
                    ln["dq"] = 1
            lines.append("|".join([deal, ln["id"], mmYYYY, f"{ln['upb']:.2f}", ln["rate"], str(ln["age"]),
                                   str(360 - ln["age"]), str(min(ln["dq"], 99)), ln["mod"], zb, zb_date, nsp,
                                   event, ln["state"]]) + "\n")
        files[period] = lines
    return files


def write(deal: str, period: str, lines: list[str]) -> None:
    (INBOUND / f"{deal}_{period.replace('-', '')}.txt").write_text("".join(lines))


def load(deal: str, period: str, expect_ok: bool) -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "CRT_INBOUND_DIR": str(INBOUND), "CRT_STORE": str(STORE)}
    proc = subprocess.run([sys.executable, "-m", "crt_perf.cli", "load", "--deal", deal, "--period", period,
                           "--log-level", "ERROR"], cwd=ROOT, env=env, capture_output=True, text=True)
    if (proc.returncode == 0) != expect_ok:
        raise SystemExit(f"setup load {deal} {period} rc={proc.returncode}\n{proc.stderr}")


def main() -> None:
    rng = random.Random(SEED)
    if INBOUND.exists():
        shutil.rmtree(INBOUND)
    INBOUND.mkdir(parents=True)
    for suffix in ("", "-wal", "-shm"):
        Path(str(STORE) + suffix).unlink(missing_ok=True)
    sims = {deal: simulate(rng, deal, n) for deal, n in DEALS.items()}
    for period in PERIODS[:2]:
        for deal in DEALS:
            write(deal, period, sims[deal][period])
            load(deal, period, expect_ok=True)
    # September: STACR is clean; the CAS file has one bad zero balance code in line 18,204.
    write("STACR-2025-DNA2", "2026-09", sims["STACR-2025-DNA2"]["2026-09"])
    load("STACR-2025-DNA2", "2026-09", expect_ok=True)
    good = sims["CAS-2024-R03"]["2026-09"]
    bad = list(good)
    parts = bad[18_203].split("|")
    parts[9] = "0l"   # a typo in the vendor's extract
    bad[18_203] = "|".join(parts)
    write("CAS-2024-R03", "2026-09", bad)
    load("CAS-2024-R03", "2026-09", expect_ok=False)
    write("CAS-2024-R03", "2026-09", good)   # vendor resend
    print("July/August loaded; September STACR loaded; September CAS load failed and the corrected "
          "file is now in data/inbound/ (not loaded yet)")


if __name__ == "__main__":
    main()
