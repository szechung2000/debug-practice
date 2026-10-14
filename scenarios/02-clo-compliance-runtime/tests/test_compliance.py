from datetime import date

import pandas as pd
import pytest

from clo_compliance import metrics
from clo_compliance.config import Limits
from clo_compliance.ratings import RatingsStore, notch_down, sp_to_moodys


def ratings_df(rows):
    df = pd.DataFrame(rows, columns=["loanx_id", "agency", "rating", "as_of"])
    df["as_of"] = pd.to_datetime(df["as_of"])
    return df


def holdings_df(rows):
    return pd.DataFrame(rows, columns=["deal_id", "position_id", "loanx_id", "obligor_id", "industry",
                                       "par", "price", "spread_bps", "is_defaulted"])


def test_sp_mapping_and_notching():
    assert sp_to_moodys("B+") == "B1"
    assert notch_down("B3") == "Caa1"
    assert notch_down("C") == "C"


def test_point_in_time_rating():
    store = RatingsStore(ratings_df([
        ("LX1", "MOODYS", "B1", "2025-01-10"),
        ("LX1", "MOODYS", "B2", "2025-09-01"),
        ("LX1", "MOODYS", "Caa1", "2026-05-01"),
    ]), date(2026, 3, 31))
    assert store.get("LX1", "MOODYS") == "B2"


def test_moodys_derived_falls_back_to_sp():
    store = RatingsStore(ratings_df([("LX2", "SP", "B", "2025-01-10")]), date(2026, 3, 31))
    assert store.moodys_derived("LX2") == "B3"
    assert store.moodys_derived("UNKNOWN") == "Caa3"


def test_obligor_concentration_sums_facilities():
    pos = holdings_df([
        ("D", "P1", "LX1A", "OB1", "Software", 1_000_000, 99, 350, 0),
        ("D", "P2", "LX1B", "OB1", "Software", 500_000, 98, 350, 0),
        ("D", "P3", "LX2A", "OB2", "Retail", 1_200_000, 97, 400, 0),
    ])
    obligor, pct = metrics.obligor_concentration(pos, 2_700_000)
    assert obligor == "OB1"
    assert pct == pytest.approx(100 * 1_500_000 / 2_700_000)


def test_ccc_excess_taken_from_lowest_price_first():
    store = RatingsStore(ratings_df([
        ("LXA", "MOODYS", "Caa1", "2025-01-01"),
        ("LXB", "MOODYS", "Caa2", "2025-01-01"),
        ("LXC", "MOODYS", "B1", "2025-01-01"),
    ]), date(2026, 3, 31))
    pos = holdings_df([
        ("D", "P1", "LXA", "OB1", "Software", 10.0, 80.0, 400, 0),
        ("D", "P2", "LXB", "OB2", "Retail", 10.0, 60.0, 400, 0),
        ("D", "P3", "LXC", "OB3", "Media", 80.0, 99.0, 400, 0),
    ])
    ccc_par, haircut = metrics.ccc_bucket(pos, store, 100.0, 7.5)
    assert ccc_par == 20.0
    # excess = 12.5: 10 of the 60-priced asset, then 2.5 of the 80-priced asset
    assert haircut == pytest.approx(10 * 0.40 + 2.5 * 0.20)


def test_run_deal_flags(tmp_path):
    store = RatingsStore(ratings_df([("LXA", "MOODYS", "B2", "2025-01-01")]), date(2026, 3, 31))
    pos = holdings_df([("D", "P1", "LXA", "OB1", "Software", 100.0, 99.0, 400, 0)])
    res = metrics.run_deal("D", pos, store, senior_notes=80.0, oc_trigger=120.0, limits=Limits())
    assert res.oc_ratio == pytest.approx(125.0)
    assert res.oc_pass and res.warf_pass
    assert not res.obligor_pass  # one obligor is 100% of the deal
