"""Build the cash forecast and write it for Treasury."""
from __future__ import annotations

import csv
import logging
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from .calendar import BusinessCalendar
from .cashflow import CashFlow, first_payment_period, position_cashflows
from .config import ForecastConfig
from .inputs import Position

log = logging.getLogger(__name__)


def build(positions: list[Position], factors: dict[str, dict[str, Decimal]], cfg: ForecastConfig,
          cal: BusinessCalendar) -> list[CashFlow]:
    flows: list[CashFlow] = []
    missing = 0
    for pos in positions:
        pool = factors.get(pos.cusip)
        if not pool:
            missing += 1
            log.error("no factors for %s (pool %s); position excluded", pos.cusip, pos.pool_number)
            continue
        first = first_payment_period(cfg.as_of, pos.program, cal)
        try:
            flows.extend(position_cashflows(pos, pool, first, cfg, cal))
        except KeyError as exc:
            missing += 1
            log.error("%s: %s; position excluded", pos.cusip, exc)
    log.info("forecast: %d cash flows from %d positions (%d excluded)", len(flows), len(positions), missing)
    return flows


def daily_totals(flows: list[CashFlow]) -> list[dict]:
    acc: dict[tuple[date, str], list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0), Decimal(0)])
    for f in flows:
        a = acc[(f.payment_date, f.account)]
        a[0] += f.principal
        a[1] += f.interest
        a[2] += f.total
    return [{"payment_date": d.isoformat(), "weekday": d.strftime("%a"), "account": acct,
             "principal": str(v[0]), "interest": str(v[1]), "total": str(v[2])}
            for (d, acct), v in sorted(acc.items())]


def check_dates(flows: list[CashFlow], cal: BusinessCalendar) -> list[str]:
    """Every payment must land on a business day."""
    problems = []
    for d in sorted({f.payment_date for f in flows}):
        if not cal.is_business_day(d):
            problems.append(f"payment date {d} ({d:%a}) is not a business day")
    return problems


def write(flows: list[CashFlow], out_dir: Path, as_of: date) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    detail = out_dir / f"mbs_cash_detail_{as_of:%Y%m%d}.csv"
    with detail.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["account", "cusip", "program", "period", "payment_date", "principal", "interest",
                    "total", "projected"])
        for f in sorted(flows, key=lambda x: (x.payment_date, x.account, x.cusip)):
            w.writerow([f.account, f.cusip, f.program, f.period, f.payment_date.isoformat(),
                        f.principal, f.interest, f.total, int(f.projected)])
    daily = out_dir / f"mbs_cash_daily_{as_of:%Y%m%d}.csv"
    rows = daily_totals(flows)
    with daily.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["payment_date"])
        w.writeheader()
        w.writerows(rows)
    log.info("wrote %s and %s", detail.name, daily.name)
    return detail, daily
