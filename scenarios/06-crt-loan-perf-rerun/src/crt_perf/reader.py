"""Stream and parse the vendor's pipe-delimited monthly performance file."""
from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

log = logging.getLogger(__name__)

# Field order of the vendor layout (subset we load).
FIELDS = (
    "deal_id", "loan_id", "reporting_period", "current_upb", "current_rate", "loan_age",
    "remaining_months", "dq_status", "modification_flag", "zero_balance_code",
    "zero_balance_date", "net_sales_proceeds", "credit_event_flag", "property_state",
)
ZERO_BALANCE_CODES = {"", "01", "02", "03", "06", "09", "15", "16", "96"}


class RecordError(ValueError):
    pass


@dataclass(frozen=True)
class Chunk:
    number: int
    first_line: int
    lines: list[str]


def parse_period(raw: str) -> date:
    """Vendor periods are MMYYYY."""
    raw = raw.strip()
    if len(raw) != 6 or not raw.isdigit():
        raise RecordError(f"bad period {raw!r}")
    month, year = int(raw[:2]), int(raw[2:])
    if not 1 <= month <= 12:
        raise RecordError(f"bad month in period {raw!r}")
    return date(year, month, 1)


def _decimal(raw: str, name: str) -> Decimal | None:
    raw = raw.strip()
    if raw == "":
        return None
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise RecordError(f"{name}: not a number {raw!r}") from exc


def parse_line(line: str) -> dict:
    parts = line.rstrip("\n").split("|")
    if len(parts) != len(FIELDS):
        raise RecordError(f"expected {len(FIELDS)} fields, got {len(parts)}")
    rec = dict(zip(FIELDS, (p.strip() for p in parts)))
    zb = rec["zero_balance_code"]
    if zb not in ZERO_BALANCE_CODES:
        raise RecordError(f"unknown zero balance code {zb!r}")
    dq = rec["dq_status"]
    if not (dq.isdigit() or dq == "XX"):
        raise RecordError(f"bad delinquency status {dq!r}")
    upb = _decimal(rec["current_upb"], "current_upb")
    if upb is None or upb < 0:
        raise RecordError(f"bad current_upb {rec['current_upb']!r}")
    return {
        "deal_id": rec["deal_id"],
        "loan_id": rec["loan_id"],
        "reporting_period": parse_period(rec["reporting_period"]).isoformat(),
        "current_upb": upb,
        "current_rate": _decimal(rec["current_rate"], "current_rate"),
        "loan_age": int(rec["loan_age"] or 0),
        "remaining_months": int(rec["remaining_months"] or 0),
        "dq_status": dq,
        "modification_flag": rec["modification_flag"] == "Y",
        "zero_balance_code": zb or None,
        "zero_balance_date": rec["zero_balance_date"] or None,
        "net_sales_proceeds": _decimal(rec["net_sales_proceeds"], "net_sales_proceeds"),
        "credit_event_flag": rec["credit_event_flag"] == "Y",
        "property_state": rec["property_state"],
    }


def count_lines(path: Path) -> int:
    with path.open("rb") as fh:
        return sum(1 for line in fh if line.strip())


def iter_chunks(path: Path, chunk_size: int) -> Iterator[Chunk]:
    with path.open(encoding="utf-8") as fh:
        buf: list[str] = []
        number, first = 1, 1
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            buf.append(line)
            if len(buf) == chunk_size:
                yield Chunk(number, first, buf)
                number, first, buf = number + 1, line_no + 1, []
        if buf:
            yield Chunk(number, first, buf)
