"""Publish pool speeds for the desk and run the pre-publication checks."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

OUTPUT_COLUMNS = [
    "deal_id", "pool_id", "period", "loan_count", "beginning_balance", "ending_balance",
    "scheduled_principal", "prepaid_principal", "liquidated_balance", "realized_loss",
    "wac", "wala", "smm", "mdr", "severity",
]
RATE_COLUMNS_PREFIX = ("cpr_", "cdr_")


class PublishError(Exception):
    pass


def rate_columns(df: pd.DataFrame) -> list[str]:
    return sorted(c for c in df.columns if c.startswith(RATE_COLUMNS_PREFIX))


def sanity_check(df: pd.DataFrame) -> list[str]:
    """Return human-readable warnings. Speeds outside [0, 1] are impossible."""
    warnings = []
    for col in rate_columns(df) + ["smm", "mdr"]:
        bad = df[(df[col] < 0) | (df[col] > 1)]
        for row in bad.itertuples(index=False):
            warnings.append(f"{col} out of range for {row.pool_id} {row.period}: {getattr(row, col):.4f}")
    return warnings


def latest_period_summary(df: pd.DataFrame) -> pd.DataFrame:
    latest = df["period"].max()
    cur = df[df["period"] == latest]
    weights = cur["beginning_balance"].fillna(0)
    if weights.sum() == 0:
        return pd.DataFrame()
    summary = (cur.assign(w=weights)
                  .groupby("deal_id")
                  .apply(lambda g: pd.Series({
                      "period": latest,
                      "pools": len(g),
                      "balance": g["ending_balance"].sum(),
                      "cpr_1m": (g["cpr_1m"] * g["w"]).sum() / g["w"].sum() if g["w"].sum() else float("nan"),
                      "cdr_1m": (g["cdr_1m"] * g["w"]).sum() / g["w"].sum() if g["w"].sum() else float("nan"),
                  }), include_groups=False))
    return summary.reset_index()


def publish(df: pd.DataFrame, path: Path, strict: bool = False) -> Path:
    warnings = sanity_check(df)
    for w in warnings[:50]:
        log.warning(w)
    if len(warnings) > 50:
        log.warning("... %d more out-of-range values", len(warnings) - 50)
    if warnings and strict:
        raise PublishError(f"{len(warnings)} out-of-range speeds; not publishing")
    out = df[OUTPUT_COLUMNS + rate_columns(df)].sort_values(["deal_id", "pool_id", "period"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    out.to_csv(tmp, index=False, float_format="%.6f")
    tmp.replace(path)
    log.info("published %d rows to %s", len(out), path)
    return path
