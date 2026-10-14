"""Map servicer rows to the warehouse model."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

log = logging.getLogger(__name__)

STATUSES = {"CURRENT", "DELINQUENT", "REPO", "CHARGED_OFF", "PAID_OFF"}
TERMINAL = {"CHARGED_OFF", "PAID_OFF"}


class RowError(ValueError):
    pass


def dq_bucket(days_past_due: int, status: str) -> str:
    """Delinquency bucket as reported in the ABS servicer report."""
    if status in TERMINAL:
        return status
    if status == "REPO":
        return "REPO"
    if days_past_due <= 0:
        return "CURRENT"
    if days_past_due < 30:
        return "1-29"
    if days_past_due < 60:
        return "30-59"
    if days_past_due < 90:
        return "60-89"
    if days_past_due < 120:
        return "90-119"
    return "120+"


def cents_to_decimal(cents: int | None) -> str:
    if cents is None:
        raise RowError("null balance")
    return str((Decimal(int(cents)) / 100).quantize(Decimal("0.01")))


@dataclass
class TransformResult:
    rows: list[dict]
    rejected: list[tuple[str, str]]


def to_warehouse(raw: dict) -> dict:
    status = (raw.get("status") or "").upper()
    if status not in STATUSES:
        raise RowError(f"unknown status {raw.get('status')!r}")
    dpd = int(raw.get("days_past_due") or 0)
    if dpd < 0:
        raise RowError(f"negative days_past_due {dpd}")
    balance = cents_to_decimal(raw.get("current_balance_cents"))
    if status in TERMINAL and Decimal(balance) != 0:
        # The platform zeroes the balance in a separate write; keep the row and
        # let the next change correct it.
        log.debug("loan %s is %s with balance %s", raw["loan_id"], status, balance)
    return {
        "loan_id": raw["loan_id"],
        "deal_id": raw["deal_id"],
        "borrower_state": raw["borrower_state"],
        "original_balance": cents_to_decimal(raw.get("original_balance_cents")),
        "current_balance": balance,
        "apr": str((Decimal(int(raw["apr_bps"])) / 10000).quantize(Decimal("0.0001"))),
        "original_term": int(raw["original_term"]),
        "remaining_term": int(raw["remaining_term"]),
        "next_due_date": raw["next_due_date"],
        "days_past_due": dpd,
        "dq_bucket": dq_bucket(dpd, status),
        "status": status,
        "vehicle_type": raw.get("vehicle_type") or "UNKNOWN",
        "ltv_pct": float(raw["ltv_pct"]) if raw.get("ltv_pct") is not None else None,
        "fico": int(raw["fico"]) if raw.get("fico") is not None else None,
        "source_updated_at": raw["updated_at"],
    }


def transform_page(raw_rows: list[dict]) -> TransformResult:
    out, rejected = [], []
    for raw in raw_rows:
        try:
            out.append(to_warehouse(raw))
        except (RowError, KeyError, TypeError, ValueError) as exc:
            rejected.append((str(raw.get("loan_id")), str(exc)))
    if rejected:
        log.warning("rejected %d rows, first: %s", len(rejected), rejected[0])
    return TransformResult(out, rejected)
