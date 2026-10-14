"""Snapshots of published speeds, and the restatement report.

Every publish keeps a dated copy of the output. The restatement report
compares the new output with the previous snapshot for periods that were
already published, so the desk knows which historical numbers moved.
"""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

COMPARE_COLUMNS = ("cpr_1m", "cpr_3m", "cdr_1m", "cdr_3m", "beginning_balance")
KEY = ["pool_id", "period"]


@dataclass(frozen=True)
class Restatement:
    pool_id: str
    period: str
    column: str
    before: float
    after: float

    @property
    def change(self) -> float:
        return self.after - self.before


def snapshot_dir(output_path: Path) -> Path:
    return output_path.parent / "snapshots"


def save_snapshot(output_path: Path, now: datetime | None = None) -> Path:
    now = now or datetime.now(timezone.utc)
    target_dir = snapshot_dir(output_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{output_path.stem}_{now:%Y%m%dT%H%M%S}.csv"
    shutil.copy2(output_path, target)
    log.info("snapshot saved: %s", target.name)
    return target


def latest_snapshot(output_path: Path, exclude: Path | None = None) -> Path | None:
    snaps = sorted(snapshot_dir(output_path).glob(f"{output_path.stem}_*.csv"))
    snaps = [s for s in snaps if exclude is None or s.resolve() != exclude.resolve()]
    return snaps[-1] if snaps else None


def compare(previous: pd.DataFrame, current: pd.DataFrame, threshold: float = 0.0005) -> list[Restatement]:
    """Changes larger than `threshold` (absolute) on periods present in both."""
    cols = [c for c in COMPARE_COLUMNS if c in previous.columns and c in current.columns]
    merged = previous[KEY + cols].merge(current[KEY + cols], on=KEY, suffixes=("_prev", "_cur"))
    out: list[Restatement] = []
    for col in cols:
        before, after = merged[f"{col}_prev"], merged[f"{col}_cur"]
        scale = 1.0 if col.startswith(("cpr", "cdr")) else max(1.0, float(before.abs().max() or 1.0))
        moved = (after - before).abs() / scale > threshold
        moved |= before.isna() != after.isna()
        for row in merged[moved].itertuples(index=False):
            out.append(Restatement(row.pool_id, row.period, col,
                                   float(getattr(row, f"{col}_prev")), float(getattr(row, f"{col}_cur"))))
    return out


def restatement_report(output_path: Path, previous: Path | None = None) -> list[Restatement]:
    prev_path = previous or latest_snapshot(output_path)
    if prev_path is None or not prev_path.exists():
        log.info("no previous snapshot; restatement report skipped")
        return []
    prev = pd.read_csv(prev_path, dtype={"pool_id": str, "period": str})
    cur = pd.read_csv(output_path, dtype={"pool_id": str, "period": str})
    changes = compare(prev, cur)
    pools = sorted({c.pool_id for c in changes})
    log.info("restatement report vs %s: %d values moved on %d pools", prev_path.name, len(changes), len(pools))
    for c in changes[:40]:
        log.info("  %s %s %s: %.6f -> %.6f", c.pool_id, c.period, c.column, c.before, c.after)
    return changes
