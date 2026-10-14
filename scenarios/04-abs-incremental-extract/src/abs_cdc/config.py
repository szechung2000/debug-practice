"""Settings for the auto ABS loan incremental extract."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
JOB_NAME = "auto_loan_incremental"


@dataclass(frozen=True)
class ExtractConfig:
    source_path: Path         # servicer OLTP replica (SQLite stands in for it)
    warehouse_path: Path
    page_size: int = 5000
    max_pages: int = 10_000   # guard against a runaway loop
    max_retries: int = 3
    retry_backoff_s: float = 0.5

    @classmethod
    def from_env(cls, source: str | None = None, warehouse: str | None = None) -> "ExtractConfig":
        return cls(
            source_path=Path(source or os.environ.get("ABS_SOURCE_DB", "data/source.db")),
            warehouse_path=Path(warehouse or os.environ.get("ABS_WAREHOUSE_DB", "data/warehouse.db")),
            page_size=int(os.environ.get("ABS_PAGE_SIZE", "5000")),
        )


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=LOG_FORMAT)
