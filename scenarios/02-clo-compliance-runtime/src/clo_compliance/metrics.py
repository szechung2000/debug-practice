"""Collateral quality and concentration tests, one deal at a time.

Each test is written to be read next to the indenture definition. The
definitions below are the ones the trustee uses in the monthly report.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

import pandas as pd

from .config import Limits
from .ratings import RatingsStore

log = logging.getLogger(__name__)


@dataclass
class DealResult:
    deal_id: str
    positions: int
    total_par: float
    max_obligor_id: str
    max_obligor_pct: float
    max_industry: str
    max_industry_pct: float
    ccc_par: float
    ccc_pct: float
    ccc_haircut: float
    defaulted_par: float
    adjusted_par: float
    oc_ratio: float
    warf: float
    was_bps: float
    obligor_pass: bool = True
    industry_pass: bool = True
    ccc_pass: bool = True
    warf_pass: bool = True
    was_pass: bool = True
    oc_pass: bool = True

    def as_row(self) -> dict:
        return asdict(self)


def obligor_concentration(positions: pd.DataFrame, total_par: float) -> tuple[str, float]:
    """Largest single obligor as % of collateral par. An obligor can have
    several facilities (term loan B, add-on, incremental) in one deal."""
    best_id, best_pct = "", 0.0
    for _, row in positions.iterrows():
        obligor_par = positions[positions["obligor_id"] == row["obligor_id"]]["par"].sum()
        pct = 100.0 * obligor_par / total_par
        if pct > best_pct or (pct == best_pct and row["obligor_id"] < best_id):
            best_id, best_pct = row["obligor_id"], pct
    return best_id, best_pct


def industry_concentration(positions: pd.DataFrame, total_par: float) -> tuple[str, float]:
    by_industry = positions.groupby("industry")["par"].sum().sort_index()
    top = by_industry.idxmax()
    return str(top), 100.0 * float(by_industry[top]) / total_par


def ccc_bucket(positions: pd.DataFrame, store: RatingsStore, total_par: float,
               limit_pct: float) -> tuple[float, float]:
    """Return (CCC par, haircut).

    CCC par above the limit is carried at market value instead of par. The
    excess is taken from the lowest-priced CCC assets first (indenture
    definition of "CCC Excess"). Defaulted assets are excluded here; they get
    their own haircut.
    """
    ccc_rows = []
    for _, row in positions.iterrows():
        if row["is_defaulted"]:
            continue
        if store.is_ccc(row["loanx_id"]):
            ccc_rows.append((row["price"], row["position_id"], row["par"]))
    ccc_par = sum(p for _, _, p in ccc_rows)
    excess = max(0.0, ccc_par - total_par * limit_pct / 100.0)
    haircut = 0.0
    for price, _, par in sorted(ccc_rows):
        if excess <= 0:
            break
        take = min(par, excess)
        haircut += take * (1.0 - price / 100.0)
        excess -= take
    return ccc_par, haircut


def defaulted_haircut(positions: pd.DataFrame) -> tuple[float, float]:
    """Defaulted assets count at the lower of market value and 30% of par."""
    par, haircut = 0.0, 0.0
    for _, row in positions[positions["is_defaulted"] == 1].iterrows():
        carrying = min(row["price"] / 100.0, 0.30) * row["par"]
        par += row["par"]
        haircut += row["par"] - carrying
    return par, haircut


def weighted_average_rating_factor(positions: pd.DataFrame, store: RatingsStore) -> float:
    """Par-weighted Moody's rating factor, excluding defaulted assets."""
    num, den = 0.0, 0.0
    for _, row in positions.iterrows():
        if row["is_defaulted"]:
            continue
        num += row["par"] * store.rating_factor(row["loanx_id"])
        den += row["par"]
    return num / den if den else 0.0


def weighted_average_spread(positions: pd.DataFrame) -> float:
    live = positions[positions["is_defaulted"] == 0]
    if live.empty:
        return 0.0
    return float((live["par"] * live["spread_bps"]).sum() / live["par"].sum())


def run_deal(deal_id: str, positions: pd.DataFrame, store: RatingsStore,
             senior_notes: float, oc_trigger: float, limits: Limits) -> DealResult:
    total_par = float(positions["par"].sum())
    obligor_id, obligor_pct = obligor_concentration(positions, total_par)
    industry, industry_pct = industry_concentration(positions, total_par)
    ccc_par, ccc_cut = ccc_bucket(positions, store, total_par, limits.max_ccc_pct)
    dflt_par, dflt_cut = defaulted_haircut(positions)
    adjusted = total_par - ccc_cut - dflt_cut
    oc_ratio = 100.0 * adjusted / senior_notes if senior_notes else float("inf")
    warf = weighted_average_rating_factor(positions, store)
    was = weighted_average_spread(positions)
    result = DealResult(
        deal_id=deal_id, positions=len(positions), total_par=round(total_par, 2),
        max_obligor_id=obligor_id, max_obligor_pct=round(obligor_pct, 4),
        max_industry=industry, max_industry_pct=round(industry_pct, 4),
        ccc_par=round(ccc_par, 2), ccc_pct=round(100.0 * ccc_par / total_par, 4),
        ccc_haircut=round(ccc_cut, 2), defaulted_par=round(dflt_par, 2),
        adjusted_par=round(adjusted, 2), oc_ratio=round(oc_ratio, 4),
        warf=round(warf, 2), was_bps=round(was, 2),
    )
    result.obligor_pass = obligor_pct <= limits.max_single_obligor_pct
    result.industry_pass = industry_pct <= limits.max_industry_pct
    result.ccc_pass = result.ccc_pct <= limits.max_ccc_pct
    result.warf_pass = warf <= limits.max_warf
    result.was_pass = was >= limits.min_was_bps
    result.oc_pass = oc_ratio >= oc_trigger
    return result
