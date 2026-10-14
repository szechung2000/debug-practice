"""Reconcile loaded loan balances to the trustee remittance report."""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .parser import parse_amount

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconResult:
    deal_id: str
    period: str
    loan_count: int
    trustee_loan_count: int
    ending_balance: Decimal
    trustee_ending_balance: Decimal

    @property
    def variance(self) -> Decimal:
        return self.ending_balance - self.trustee_ending_balance

    def is_break(self, tolerance: Decimal) -> bool:
        return abs(self.variance) > tolerance or self.loan_count != self.trustee_loan_count


def read_trustee(path: Path) -> dict[tuple[str, str], tuple[int, Decimal]]:
    if not path.exists():
        log.warning("no trustee remittance file at %s; reconciliation skipped", path)
        return {}
    out: dict[tuple[str, str], tuple[int, Decimal]] = {}
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            key = (row["deal_id"].strip().upper(), row["period"].strip())
            out[key] = (int(row["loan_count"]), parse_amount(row["ending_balance"]))
    return out


def reconcile(rows: list[dict], trustee: dict[tuple[str, str], tuple[int, Decimal]]) -> list[ReconResult]:
    totals: dict[tuple[str, str], list] = {}
    for row in rows:
        key = (row["deal_id"], row["period"])
        acc = totals.setdefault(key, [0, Decimal("0")])
        acc[0] += 1
        acc[1] += Decimal(row["ending_balance"])
    results = []
    for key, (count, balance) in sorted(totals.items()):
        if key not in trustee:
            log.info("recon %s %s: no trustee figures yet", *key)
            continue
        t_count, t_balance = trustee[key]
        results.append(ReconResult(key[0], key[1], count, t_count, balance, t_balance))
    return results


def report(results: list[ReconResult], tolerance: Decimal) -> int:
    breaks = 0
    for r in results:
        if r.is_break(tolerance):
            breaks += 1
            log.warning("RECON BREAK %s %s: loans %d vs %d, ending balance %s vs trustee %s (variance %s)",
                        r.deal_id, r.period, r.loan_count, r.trustee_loan_count,
                        r.ending_balance, r.trustee_ending_balance, r.variance)
        else:
            log.info("recon ok %s %s: %d loans, variance %s", r.deal_id, r.period, r.loan_count, r.variance)
    return breaks
