"""Load trustee pool-level remittance files and trustee correction files.

Remittance files: one per deal per month, `<deal>_<YYYYMM>.csv`.
Correction files: the trustee resends a pool-period row when a servicer
restates. Files are named `correction_<period YYYYMM>_<sent YYYYMMDD>.csv` and
replace the remittance row for the same (pool, period).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

REMIT_RE = re.compile(r"^(?P<deal>[A-Z0-9-]+)_(?P<period>\d{6})\.csv$")
CORR_RE = re.compile(r"^correction_(?P<period>\d{6})_(?P<sent>\d{8})\.csv$")

COLUMNS = {
    "deal_id": "string",
    "pool_id": "string",
    "period": "string",
    "loan_count": "int64",
    "ending_balance": "float64",
    "scheduled_principal": "float64",
    "curtailments": "float64",
    "payoffs": "float64",
    "liquidated_balance": "float64",
    "realized_loss": "float64",
    "wac": "float64",
    "wala": "int64",
}
AMOUNT_COLUMNS = ["ending_balance", "scheduled_principal", "curtailments", "payoffs",
                  "liquidated_balance", "realized_loss"]


class LoadError(Exception):
    pass


def _read(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=COLUMNS)
    missing = sorted(set(COLUMNS) - set(df.columns))
    if missing:
        raise LoadError(f"{path.name}: missing columns {missing}")
    df = df[list(COLUMNS)]
    df["source_file"] = path.name
    return df


def _validate(df: pd.DataFrame, name: str) -> None:
    neg = (df[AMOUNT_COLUMNS] < 0).any(axis=1)
    if neg.any():
        raise LoadError(f"{name}: negative amounts on {int(neg.sum())} rows")
    bad_period = ~df["period"].str.fullmatch(r"\d{4}-\d{2}")
    if bad_period.any():
        raise LoadError(f"{name}: bad period values {df.loc[bad_period, 'period'].unique()[:3].tolist()}")


def load_remittances(remit_dir: Path) -> pd.DataFrame:
    files = sorted(p for p in remit_dir.glob("*.csv") if REMIT_RE.match(p.name))
    if not files:
        raise LoadError(f"no remittance files in {remit_dir}")
    frames = []
    for path in files:
        df = _read(path)
        m = REMIT_RE.match(path.name)
        expected_period = f"{m['period'][:4]}-{m['period'][4:]}"
        wrong = df["period"] != expected_period
        if wrong.any():
            raise LoadError(f"{path.name}: {int(wrong.sum())} rows not for period {expected_period}")
        _validate(df, path.name)
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    dupes = out.duplicated(["pool_id", "period"])
    if dupes.any():
        raise LoadError(f"duplicate pool-periods across remittance files: "
                        f"{out.loc[dupes, ['pool_id', 'period']].head(3).values.tolist()}")
    log.info("remittances: %d pool-periods from %d files", len(out), len(files))
    return out


def load_corrections(corr_dir: Path) -> pd.DataFrame:
    if not corr_dir.exists():
        return pd.DataFrame(columns=list(COLUMNS) + ["source_file", "sent_date"])
    frames = []
    for path in sorted(corr_dir.glob("correction_*.csv")):
        m = CORR_RE.match(path.name)
        if not m:
            log.warning("ignoring %s: unexpected name", path.name)
            continue
        df = _read(path)
        _validate(df, path.name)
        df["sent_date"] = m["sent"]
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=list(COLUMNS) + ["source_file", "sent_date"])
    out = pd.concat(frames, ignore_index=True)
    log.info("corrections: %d pool-period rows from %d files", len(out), len(frames))
    return out


def apply_corrections(remits: pd.DataFrame, corrections: pd.DataFrame) -> pd.DataFrame:
    """Replace remittance rows with the latest correction for the same pool-period."""
    if corrections.empty:
        return remits
    corrections = corrections.sort_values("sent_date", kind="mergesort").drop(columns="sent_date")
    unknown = corrections.merge(remits[["pool_id", "period"]], how="left", indicator=True)
    orphans = unknown[unknown["_merge"] == "left_only"]
    if not orphans.empty:
        log.warning("%d corrections have no remittance row; they are added as new rows", len(orphans))
    combined = pd.concat([remits, corrections], ignore_index=True)
    combined = combined.drop_duplicates(["pool_id", "period"], keep="last").reset_index(drop=True)
    log.info("applied corrections: %d pool-periods replaced", len(corrections) - len(orphans))
    return combined
