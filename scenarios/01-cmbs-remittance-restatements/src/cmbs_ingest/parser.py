"""Parse CREFC-style loan periodic update (LPU) files into typed records."""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .manifest import ManifestEntry

log = logging.getLogger(__name__)

DATE_FORMATS = ("%Y%m%d", "%Y-%m-%d", "%m/%d/%Y")
DELINQUENCY_CODES = {"0", "A", "B", "1", "2", "3", "4", "5", "6", "7", "9"}


class ParseError(Exception):
    pass


@dataclass
class LoanPeriodic:
    deal_id: str
    loan_id: str
    period: str
    distribution_date: date
    determination_date: date
    beginning_balance: Decimal
    scheduled_principal: Decimal
    unscheduled_principal: Decimal
    ending_balance: Decimal
    current_rate: Decimal
    paid_through_date: date | None
    delinquency_status: str
    servicer_comment: str
    source_file: str
    servicer: str
    received_at: str

    @property
    def balance_rollforward_gap(self) -> Decimal:
        expected = self.beginning_balance - self.scheduled_principal - self.unscheduled_principal
        return self.ending_balance - expected


def parse_amount(raw: str) -> Decimal:
    """Servicer amounts may carry thousands separators, $ signs, or
    accounting negatives such as (1,234.56)."""
    text = (raw or "").strip().replace(",", "").replace("$", "")
    if text in ("", "-", "NA", "N/A"):
        return Decimal("0")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ParseError(f"bad amount {raw!r}") from exc
    return -value if negative else value


def parse_rate(raw: str) -> Decimal:
    """Rates arrive either as decimals (0.0525) or as percents (5.25)."""
    value = parse_amount(raw)
    return value / 100 if value > 1 else value


def parse_date(raw: str, allow_blank: bool = False) -> date | None:
    text = (raw or "").strip()
    if not text:
        if allow_blank:
            return None
        raise ParseError("blank date")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ParseError(f"bad date {raw!r}")


def parse_file(entry: ManifestEntry, required_columns: tuple[str, ...]) -> list[LoanPeriodic]:
    records: list[LoanPeriodic] = []
    errors = 0
    with Path(entry.path).open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header = [h.strip().lower() for h in (reader.fieldnames or [])]
        missing = [c for c in required_columns if c not in header]
        if missing:
            raise ParseError(f"{entry.file_name}: missing columns {missing}")
        reader.fieldnames = header
        for line_no, row in enumerate(reader, start=2):
            try:
                rec = _parse_row(row, entry)
            except ParseError as exc:
                errors += 1
                log.error("%s line %d: %s", entry.file_name, line_no, exc)
                continue
            if rec.deal_id != entry.deal_id:
                errors += 1
                log.error("%s line %d: transaction_id %s does not match file deal %s",
                          entry.file_name, line_no, rec.deal_id, entry.deal_id)
                continue
            records.append(rec)
    if errors and errors > 0.02 * max(len(records), 1):
        raise ParseError(f"{entry.file_name}: {errors} bad rows, above the 2% threshold")
    log.debug("%s: %d records", entry.file_name, len(records))
    return records


def _parse_row(row: dict[str, str], entry: ManifestEntry) -> LoanPeriodic:
    status = (row.get("delinquency_status") or "0").strip().upper()
    if status not in DELINQUENCY_CODES:
        raise ParseError(f"unknown delinquency status {status!r}")
    loan_id = (row.get("loan_id") or "").strip()
    if not loan_id:
        raise ParseError("blank loan_id")
    return LoanPeriodic(
        deal_id=row["transaction_id"].strip().upper(),
        loan_id=loan_id,
        period=entry.period,
        distribution_date=parse_date(row["distribution_date"]),
        determination_date=parse_date(row["determination_date"]),
        beginning_balance=parse_amount(row["beginning_balance"]),
        scheduled_principal=parse_amount(row["scheduled_principal"]),
        unscheduled_principal=parse_amount(row["unscheduled_principal"]),
        ending_balance=parse_amount(row["ending_balance"]),
        current_rate=parse_rate(row["current_rate"]),
        paid_through_date=parse_date(row.get("paid_through_date", ""), allow_blank=True),
        delinquency_status=status,
        servicer_comment=(row.get("servicer_comment") or "").strip()[:500],
        source_file=entry.file_name,
        servicer=entry.servicer,
        received_at=entry.received_at,
    )
