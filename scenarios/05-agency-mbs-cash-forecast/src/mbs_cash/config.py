"""Settings for the agency MBS principal and interest cash forecast."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


@dataclass(frozen=True)
class Program:
    """Payment rules for one agency program."""
    code: str
    payment_day: int        # nominal day of month the investor is paid
    description: str


PROGRAMS: dict[str, Program] = {
    "UMBS": Program("UMBS", 25, "Fannie Mae / Freddie Mac UMBS (55-day)"),
    "FHLMC_GOLD": Program("FHLMC_GOLD", 15, "Freddie Mac Gold PC, legacy 45-day"),
    "GNMA_I": Program("GNMA_I", 15, "Ginnie Mae I"),
    "GNMA_II": Program("GNMA_II", 20, "Ginnie Mae II"),
}


@dataclass(frozen=True)
class ForecastConfig:
    data_dir: Path
    output_dir: Path
    as_of: date
    horizon_months: int = 3
    # Prepayment assumption per program for projected months (annual CPR).
    cpr: dict[str, Decimal] = field(default_factory=lambda: {
        "UMBS": Decimal("0.065"), "FHLMC_GOLD": Decimal("0.080"),
        "GNMA_I": Decimal("0.090"), "GNMA_II": Decimal("0.075"),
    })
    # Monthly scheduled amortisation assumption for projected months.
    scheduled_amort: Decimal = Decimal("0.0021")

    @property
    def positions_path(self) -> Path:
        return self.data_dir / "positions.csv"

    @property
    def factors_path(self) -> Path:
        return self.data_dir / "factors.csv"

    @property
    def holidays_path(self) -> Path:
        return self.data_dir / "fed_holidays.csv"

    @classmethod
    def build(cls, data: str | None, out: str | None, as_of: str | None, horizon: int | None) -> "ForecastConfig":
        return cls(
            data_dir=Path(data or os.environ.get("MBS_DATA_DIR", "data/input")),
            output_dir=Path(out or os.environ.get("MBS_OUTPUT_DIR", "data/output")),
            as_of=date.fromisoformat(as_of) if as_of else date.today(),
            horizon_months=horizon or int(os.environ.get("MBS_HORIZON_MONTHS", "3")),
        )


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=LOG_FORMAT)
