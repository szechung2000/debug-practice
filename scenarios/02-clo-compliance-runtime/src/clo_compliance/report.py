"""Write the compliance results and the exceptions list for the portfolio managers."""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from .metrics import DealResult

log = logging.getLogger(__name__)

TESTS = ("obligor_pass", "industry_pass", "ccc_pass", "warf_pass", "was_pass", "oc_pass")


def write_results(results: list[DealResult], out_dir: Path, as_of: date) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([r.as_row() for r in results]).sort_values("deal_id")
    path = out_dir / f"compliance_{as_of:%Y%m%d}.csv"
    tmp = path.with_suffix(".csv.tmp")
    df.to_csv(tmp, index=False, float_format="%.4f")
    tmp.replace(path)
    log.info("wrote %s (%d deals)", path, len(df))
    return path


def write_exceptions(results: list[DealResult], out_dir: Path, as_of: date) -> Path:
    exceptions = []
    for r in results:
        failed = [t.removesuffix("_pass") for t in TESTS if not getattr(r, t)]
        if failed:
            exceptions.append({"deal_id": r.deal_id, "failed_tests": failed,
                               "oc_ratio": r.oc_ratio, "ccc_pct": r.ccc_pct, "warf": r.warf})
    path = out_dir / f"exceptions_{as_of:%Y%m%d}.json"
    path.write_text(json.dumps({"as_of": as_of.isoformat(), "exceptions": exceptions}, indent=2))
    log.info("%d deals with at least one failing test", len(exceptions))
    return path
