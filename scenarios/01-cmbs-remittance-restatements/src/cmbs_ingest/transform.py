"""Business rules: pick the current version of each loan record and derive fields."""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from .parser import LoanPeriodic

log = logging.getLogger(__name__)

ROLLFORWARD_TOLERANCE = Decimal("1.00")
DQ_BUCKETS = {
    "0": "CURRENT", "A": "GRACE", "B": "GRACE",
    "1": "30", "2": "60", "3": "90+", "4": "MATURED_PERFORMING",
    "5": "MATURED_NONPERFORMING", "6": "90+", "7": "FORECLOSURE", "9": "REO",
}


@dataclass
class TransformStats:
    input_records: int = 0
    superseded: int = 0
    rollforward_breaks: int = 0
    by_deal_period: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))


def select_latest_versions(records: list[LoanPeriodic], stats: TransformStats) -> list[LoanPeriodic]:
    """A restated file replaces the earlier file for the same deal and period.

    The servicer may restate only some loans, so the rule works per loan:
    for each (deal, loan, period) keep the record from the copy that the
    collector received last.
    """
    stats.input_records += len(records)
    ordered = sorted(records, key=lambda r: (r.deal_id, r.loan_id, r.period, r.received_at))
    latest: dict[tuple[str, str, str], LoanPeriodic] = {}
    for rec in ordered:
        key = (rec.deal_id, rec.loan_id, rec.period)
        if key in latest:
            stats.superseded += 1
            log.debug("loan %s %s: %s supersedes %s", rec.loan_id, rec.period,
                      rec.source_file, latest[key].source_file)
        latest[key] = rec
    return list(latest.values())


def check_rollforward(records: list[LoanPeriodic], stats: TransformStats) -> list[LoanPeriodic]:
    """Flag loans whose ending balance does not roll from the beginning balance.

    A break does not stop the load: servicers often book late adjustments
    that the next period corrects. The asset manager team reviews the log.
    """
    for rec in records:
        gap = rec.balance_rollforward_gap
        if abs(gap) > ROLLFORWARD_TOLERANCE:
            stats.rollforward_breaks += 1
            log.warning("rollforward break %s/%s %s: gap %s", rec.deal_id, rec.loan_id, rec.period, gap)
    return records


def to_rows(records: list[LoanPeriodic], stats: TransformStats) -> list[dict]:
    rows = []
    for rec in records:
        stats.by_deal_period[(rec.deal_id, rec.period)] += 1
        principal = rec.scheduled_principal + rec.unscheduled_principal
        rows.append({
            "deal_id": rec.deal_id,
            "loan_id": rec.loan_id,
            "period": rec.period,
            "distribution_date": rec.distribution_date.isoformat(),
            "determination_date": rec.determination_date.isoformat(),
            "beginning_balance": str(rec.beginning_balance),
            "scheduled_principal": str(rec.scheduled_principal),
            "unscheduled_principal": str(rec.unscheduled_principal),
            "total_principal": str(principal),
            "ending_balance": str(rec.ending_balance),
            "current_rate": str(rec.current_rate),
            "paid_through_date": rec.paid_through_date.isoformat() if rec.paid_through_date else None,
            "delinquency_status": rec.delinquency_status,
            "dq_bucket": DQ_BUCKETS.get(rec.delinquency_status, "UNKNOWN"),
            "is_paid_off": int(rec.ending_balance == 0 and rec.beginning_balance > 0),
            "servicer": rec.servicer,
            "source_file": rec.source_file,
            "received_at": rec.received_at,
        })
    return rows


def run_transform(records: list[LoanPeriodic]) -> tuple[list[dict], TransformStats]:
    stats = TransformStats()
    current = select_latest_versions(records, stats)
    current = check_rollforward(current, stats)
    rows = to_rows(current, stats)
    log.info("transform: %d in, %d superseded, %d rollforward breaks, %d out",
             stats.input_records, stats.superseded, stats.rollforward_breaks, len(rows))
    return rows, stats
