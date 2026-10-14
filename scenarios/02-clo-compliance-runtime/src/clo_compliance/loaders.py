"""Read trustee holdings, the agency ratings history, and deal capital structures."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

HOLDINGS_DTYPES = {
    "deal_id": "string",
    "position_id": "string",
    "loanx_id": "string",
    "obligor_id": "string",
    "obligor_name": "string",
    "industry": "string",
    "par": "float64",
    "price": "float64",
    "spread_bps": "float64",
    "is_defaulted": "int64",
}
RATINGS_DTYPES = {"loanx_id": "string", "agency": "string", "rating": "string"}
DEALS_DTYPES = {"deal_id": "string", "senior_notes": "float64", "oc_trigger": "float64"}


class InputError(Exception):
    pass


def _require(df: pd.DataFrame, cols: dict, name: str) -> None:
    missing = sorted(set(cols) - set(df.columns))
    if missing:
        raise InputError(f"{name}: missing columns {missing}")


def load_holdings(path: Path, as_of) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=HOLDINGS_DTYPES, parse_dates=["settle_date"])
    _require(df, HOLDINGS_DTYPES, path.name)
    before = len(df)
    # Trades that have not settled are not collateral yet.
    df = df[df["settle_date"].dt.date <= as_of].copy()
    if df["position_id"].duplicated().any():
        dupes = df.loc[df["position_id"].duplicated(), "position_id"].head(5).tolist()
        raise InputError(f"{path.name}: duplicate position_id values, for example {dupes}")
    if (df["par"] <= 0).any():
        raise InputError(f"{path.name}: non-positive par on {(df['par'] <= 0).sum()} rows")
    log.info("holdings: %d positions (%d unsettled excluded) across %d deals",
             len(df), before - len(df), df["deal_id"].nunique())
    return df.reset_index(drop=True)


def load_ratings(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=RATINGS_DTYPES, parse_dates=["as_of"])
    _require(df, {**RATINGS_DTYPES, "as_of": None}, path.name)
    df["agency"] = df["agency"].str.upper()
    unknown = set(df["agency"].dropna().unique()) - {"MOODYS", "SP"}
    if unknown:
        log.warning("ratings: ignoring agencies %s", sorted(unknown))
        df = df[df["agency"].isin(["MOODYS", "SP"])]
    log.info("ratings history: %d actions for %d instruments", len(df), df["loanx_id"].nunique())
    return df.reset_index(drop=True)


def load_deals(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=DEALS_DTYPES)
    _require(df, DEALS_DTYPES, path.name)
    return df.set_index("deal_id")
