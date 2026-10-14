"""Indenture limits and runtime settings for the daily CLO compliance job."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


@dataclass(frozen=True)
class Limits:
    """Standard BSL CLO 2.0 limits. Deal-level overrides are not supported yet."""
    max_single_obligor_pct: float = 2.0
    max_industry_pct: float = 15.0
    max_ccc_pct: float = 7.5
    max_warf: int = 3000
    min_was_bps: int = 330


@dataclass(frozen=True)
class JobConfig:
    data_dir: Path
    output_dir: Path
    as_of: date
    limits: Limits = Limits()

    @property
    def holdings_path(self) -> Path:
        return self.data_dir / "holdings.csv"

    @property
    def ratings_path(self) -> Path:
        return self.data_dir / "ratings_history.csv"

    @property
    def deals_path(self) -> Path:
        return self.data_dir / "deals.csv"

    @classmethod
    def build(cls, data_dir: str | None, output_dir: str | None, as_of: str | None) -> "JobConfig":
        data = Path(data_dir or os.environ.get("CLO_DATA_DIR", "data/input"))
        out = Path(output_dir or os.environ.get("CLO_OUTPUT_DIR", "data/output"))
        run_date = date.fromisoformat(as_of) if as_of else date.today()
        return cls(data, out, run_date)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=LOG_FORMAT)
