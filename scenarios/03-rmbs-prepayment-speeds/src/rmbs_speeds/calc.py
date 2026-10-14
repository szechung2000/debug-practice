"""Pool-level prepayment, default and loss speeds.

Definitions (as used by the trading desk and in the investor reports):

  beginning balance  = the pool's ending balance in the prior period
  SMM   = (curtailments + payoffs) / (beginning balance - scheduled principal)
  CPR   = 1 - (1 - SMM) ** 12
  MDR   = liquidated balance / (beginning balance - scheduled principal)
  CDR   = 1 - (1 - MDR) ** 12
  severity = realized loss / liquidated balance

Trailing windows average the monthly rates before annualising.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def annualise(monthly: pd.Series | float) -> pd.Series | float:
    return 1.0 - (1.0 - monthly) ** 12


def add_beginning_balance(df: pd.DataFrame) -> pd.DataFrame:
    """The trustee files do not carry a beginning balance that we trust for
    every servicer, so we roll it from the prior period's ending balance."""
    df = df.copy()
    df["beginning_balance"] = df.groupby("pool_id")["ending_balance"].shift(1)
    return df


def add_monthly_rates(df: pd.DataFrame, min_balance: float) -> pd.DataFrame:
    df = df.copy()
    base = df["beginning_balance"] - df["scheduled_principal"]
    usable = df["beginning_balance"].notna() & (df["beginning_balance"] >= min_balance) & (base > 0)
    prepay = df["curtailments"] + df["payoffs"]
    df["prepaid_principal"] = prepay
    df["smm"] = np.where(usable, prepay / base.where(base > 0), np.nan)
    df["mdr"] = np.where(usable, df["liquidated_balance"] / base.where(base > 0), np.nan)
    df["severity"] = np.where(df["liquidated_balance"] > 0,
                              df["realized_loss"] / df["liquidated_balance"].where(df["liquidated_balance"] > 0),
                              np.nan)
    df["cpr_1m"] = annualise(df["smm"])
    df["cdr_1m"] = annualise(df["mdr"])
    return df


def add_trailing_windows(df: pd.DataFrame, windows: tuple[int, ...]) -> pd.DataFrame:
    df = df.copy()
    grouped = df.groupby("pool_id", sort=False)
    for w in windows:
        if w == 1:
            continue
        smm_avg = grouped["smm"].transform(lambda s, w=w: s.rolling(w, min_periods=w).mean())
        mdr_avg = grouped["mdr"].transform(lambda s, w=w: s.rolling(w, min_periods=w).mean())
        df[f"cpr_{w}m"] = annualise(smm_avg)
        df[f"cdr_{w}m"] = annualise(mdr_avg)
    return df


def balance_roll_breaks(df: pd.DataFrame, tolerance: float) -> pd.DataFrame:
    """Rows where beginning - principal paid - liquidated != ending."""
    has_prior = df["beginning_balance"].notna()
    expected = (df["beginning_balance"] - df["scheduled_principal"] - df["prepaid_principal"]
                - df["liquidated_balance"])
    gap = (df["ending_balance"] - expected).abs()
    return df.loc[has_prior & (gap > tolerance), ["deal_id", "pool_id", "period", "beginning_balance",
                                                 "ending_balance"]].assign(gap=gap)


def compute_speeds(df: pd.DataFrame, windows: tuple[int, ...], min_balance: float,
                   roll_tolerance: float) -> pd.DataFrame:
    out = add_beginning_balance(df)
    out = add_monthly_rates(out, min_balance)
    out = add_trailing_windows(out, windows)
    breaks = balance_roll_breaks(out, roll_tolerance)
    for row in breaks.itertuples(index=False):
        log.warning("balance roll break %s %s: gap %.2f", row.pool_id, row.period, row.gap)
    log.info("speeds: %d pool-periods, %d with rates, %d roll breaks",
             len(out), int(out["smm"].notna().sum()), len(breaks))
    return out
