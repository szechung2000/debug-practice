import math

import pandas as pd
import pytest

from rmbs_speeds import calc, loader, publish


def frame(rows):
    cols = ["deal_id", "pool_id", "period", "loan_count", "ending_balance", "scheduled_principal",
            "curtailments", "payoffs", "liquidated_balance", "realized_loss", "wac", "wala"]
    return pd.DataFrame(rows, columns=cols)


def pool_rows():
    # beginning 1,000,000 -> each month: 1,000 scheduled, 10,000 prepaid, 0 liquidated
    rows, bal = [], 1_000_000.0
    for i, period in enumerate(["2025-10", "2025-11", "2025-12", "2026-01"]):
        if i:
            bal = bal - 1_000 - 10_000
        rows.append(("D", "D-G1", period, 10, bal, 1_000.0, 2_000.0, 8_000.0, 0.0, 0.0, 6.0, 12 + i))
    return rows


def test_annualise():
    assert calc.annualise(0.01) == pytest.approx(0.11361, abs=1e-5)


def test_cpr_matches_definition():
    out = calc.compute_speeds(frame(pool_rows()), (1, 3), min_balance=0, roll_tolerance=1)
    second = out[out["period"] == "2025-11"].iloc[0]
    smm = 10_000 / (1_000_000 - 1_000)
    assert second["smm"] == pytest.approx(smm)
    assert second["cpr_1m"] == pytest.approx(1 - (1 - smm) ** 12)
    assert math.isnan(out[out["period"] == "2025-10"].iloc[0]["smm"])


def test_three_month_window_needs_three_months():
    out = calc.compute_speeds(frame(pool_rows()), (1, 3), min_balance=0, roll_tolerance=1)
    assert out["cpr_3m"].notna().sum() == 1


def test_corrections_replace_rows():
    remits = frame(pool_rows())
    corr = frame([("D", "D-G1", "2025-11", 10, 980_000.0, 1_000.0, 2_000.0, 17_000.0, 0.0, 0.0, 6.0, 13)])
    corr["source_file"] = "correction_202511_20251220.csv"
    corr["sent_date"] = "20251220"
    out = loader.apply_corrections(remits, corr)
    assert len(out) == 4
    nov = out[out["period"] == "2025-11"].iloc[0]
    assert nov["payoffs"] == 17_000.0


def test_sanity_check_flags_impossible_speeds():
    df = pd.DataFrame({"pool_id": ["P"], "period": ["2026-01"], "smm": [1.2], "mdr": [0.0],
                       "cpr_1m": [0.5], "cdr_1m": [0.0]})
    assert len(publish.sanity_check(df)) == 1
