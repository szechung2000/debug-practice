"""Runtime configuration for the CMBS loan periodic ingestion job."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


@dataclass(frozen=True)
class IngestConfig:
    landing_dir: Path
    warehouse_path: Path
    manifest_name: str = "manifest.csv"
    trustee_file: str = "trustee_remittance.csv"
    # Servicers report to the cent; the trustee rounds per loan, so allow a
    # small absolute variance per deal before we flag a break.
    recon_tolerance: Decimal = Decimal("5.00")
    fail_on_recon_break: bool = False
    accepted_servicers: tuple[str, ...] = ("MIDLAND", "KEYBANK", "WELLS", "TRIMONT", "PNC")
    required_columns: tuple[str, ...] = field(default=(
        "transaction_id",
        "loan_id",
        "distribution_date",
        "determination_date",
        "beginning_balance",
        "scheduled_principal",
        "unscheduled_principal",
        "ending_balance",
        "current_rate",
        "paid_through_date",
        "delinquency_status",
    ))

    @property
    def manifest_path(self) -> Path:
        return self.landing_dir / self.manifest_name

    @property
    def trustee_path(self) -> Path:
        return self.landing_dir / self.trustee_file

    @classmethod
    def from_env(cls, landing_dir: str | None = None, warehouse_path: str | None = None) -> "IngestConfig":
        landing = landing_dir or os.environ.get("CMBS_LANDING_DIR", "data/landing")
        warehouse = warehouse_path or os.environ.get("CMBS_WAREHOUSE", "data/warehouse.db")
        tol = Decimal(os.environ.get("CMBS_RECON_TOLERANCE", "5.00"))
        strict = os.environ.get("CMBS_FAIL_ON_BREAK", "0") == "1"
        return cls(Path(landing), Path(warehouse), recon_tolerance=tol, fail_on_recon_break=strict)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=LOG_FORMAT)
