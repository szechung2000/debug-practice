"""Daily reconciliation: warehouse current state vs the servicer replica."""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from .transform import dq_bucket

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BucketDiff:
    bucket: str
    source_loans: int
    warehouse_loans: int
    source_balance_cents: int
    warehouse_balance_cents: int

    @property
    def ok(self) -> bool:
        return (self.source_loans == self.warehouse_loans
                and abs(self.source_balance_cents - self.warehouse_balance_cents) <= 1 * self.source_loans)


def _by_bucket(rows) -> dict[str, list[int]]:
    acc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for status, dpd, n, bal in rows:
        b = dq_bucket(int(dpd or 0), str(status).upper())
        acc[b][0] += int(n)
        acc[b][1] += int(bal or 0)
    return acc


def reconcile(source_rows, warehouse_rows) -> list[BucketDiff]:
    src, wh = _by_bucket(source_rows), _by_bucket(warehouse_rows)
    diffs = []
    for bucket in sorted(set(src) | set(wh)):
        s, w = src.get(bucket, [0, 0]), wh.get(bucket, [0, 0])
        diffs.append(BucketDiff(bucket, s[0], w[0], s[1], w[1]))
    return diffs


def log_report(diffs: list[BucketDiff]) -> int:
    breaks = 0
    for d in diffs:
        level = logging.INFO if d.ok else logging.WARNING
        if not d.ok:
            breaks += 1
        log.log(level, "%-11s source %7d loans %16.2f | warehouse %7d loans %16.2f %s",
                d.bucket, d.source_loans, d.source_balance_cents / 100, d.warehouse_loans,
                d.warehouse_balance_cents / 100, "" if d.ok else "<-- BREAK")
    return breaks
