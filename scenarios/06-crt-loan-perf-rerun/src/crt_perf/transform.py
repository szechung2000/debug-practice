"""Derived fields used by the CRT surveillance and loss analytics."""
from __future__ import annotations

from decimal import Decimal

CREDIT_EVENT_ZB = {"02", "03", "09", "15"}   # short sale, third-party sale, REO, note sale
PREPAY_ZB = {"01"}


def dq_bucket(dq_status: str) -> str:
    if dq_status == "XX":
        return "UNKNOWN"
    months = int(dq_status)
    if months == 0:
        return "CURRENT"
    if months == 1:
        return "30"
    if months == 2:
        return "60"
    if months <= 5:
        return "90-179"
    return "180+"


def event_type(rec: dict) -> str | None:
    zb = rec["zero_balance_code"]
    if zb is None:
        return None
    if zb in PREPAY_ZB:
        return "PREPAY"
    if zb in CREDIT_EVENT_ZB or rec["credit_event_flag"]:
        return "CREDIT_EVENT"
    return "OTHER_REMOVAL"


def enrich(rec: dict, prior_upb: Decimal | None) -> dict:
    """Add surveillance fields. `prior_upb` is last month's UPB if we have it."""
    out = dict(rec)
    out["dq_bucket"] = dq_bucket(rec["dq_status"])
    out["event_type"] = event_type(rec)
    out["is_60_plus"] = out["dq_bucket"] in ("60", "90-179", "180+")
    loss = None
    if out["event_type"] == "CREDIT_EVENT" and prior_upb is not None and rec["net_sales_proceeds"] is not None:
        loss = max(Decimal("0"), prior_upb - rec["net_sales_proceeds"])
    out["estimated_loss"] = loss
    out["prior_upb"] = prior_upb
    return out


def to_db_row(rec: dict) -> tuple:
    def s(v):
        return None if v is None else str(v)
    return (
        rec["deal_id"], rec["loan_id"], rec["reporting_period"], s(rec["current_upb"]), s(rec["current_rate"]),
        rec["loan_age"], rec["remaining_months"], rec["dq_status"], rec["dq_bucket"], int(rec["is_60_plus"]),
        int(rec["modification_flag"]), rec["zero_balance_code"], rec["zero_balance_date"], rec["event_type"],
        s(rec["net_sales_proceeds"]), s(rec["prior_upb"]), s(rec["estimated_loss"]), rec["property_state"],
    )
