"""Settings for the RMBS prepayment and default speeds job."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


@dataclass(frozen=True)
class SpeedsConfig:
    remit_dir: Path
    corrections_dir: Path
    output_path: Path
    # Months in the trailing windows published to the desk.
    windows: tuple[int, ...] = (1, 3, 6, 12)
    # Balance roll tolerance per pool, in dollars.
    roll_tolerance: float = 1.0
    # Pools below this balance are too small for meaningful speeds.
    min_balance: float = 250_000.0

    @classmethod
    def build(cls, base: str | None = None, output: str | None = None) -> "SpeedsConfig":
        root = Path(base or os.environ.get("RMBS_DATA_DIR", "data"))
        out = Path(output or os.environ.get("RMBS_OUTPUT", str(root / "output" / "pool_speeds.csv")))
        return cls(root / "remits", root / "corrections", out)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=LOG_FORMAT)
