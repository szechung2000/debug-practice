"""Settings for the CRT (CAS / STACR) loan-level performance load."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(threadName)-10s %(name)s: %(message)s"


@dataclass(frozen=True)
class LoadConfig:
    inbound_dir: Path
    store_path: Path
    chunk_size: int = 5000
    workers: int = 4
    max_bad_rows: int = 0          # vendor files must be clean; any bad row fails the chunk
    busy_timeout_ms: int = 30_000

    def file_for(self, deal_id: str, period: str) -> Path:
        """Vendor naming: <deal>_<YYYYMM>.txt (pipe-delimited, no header)."""
        return self.inbound_dir / f"{deal_id}_{period.replace('-', '')}.txt"

    @classmethod
    def from_env(cls, inbound: str | None = None, store: str | None = None) -> "LoadConfig":
        return cls(
            inbound_dir=Path(inbound or os.environ.get("CRT_INBOUND_DIR", "data/inbound")),
            store_path=Path(store or os.environ.get("CRT_STORE", "data/crt_store.db")),
            chunk_size=int(os.environ.get("CRT_CHUNK_SIZE", "5000")),
            workers=int(os.environ.get("CRT_WORKERS", "4")),
        )


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=LOG_FORMAT)
