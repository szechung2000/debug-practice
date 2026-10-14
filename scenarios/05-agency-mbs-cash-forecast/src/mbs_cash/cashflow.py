"""Expected principal and interest per position per payment month.

For payment month M:
  principal = original face x (factor[M-1] - factor[M])
  interest  = original face x factor[M-1] x coupon / 12
The factor for month M is published by the agency early in month M. For
months whose factor is not published yet we project it from the CPR and
scheduled amortisation assumptions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from .calendar import BusinessCalendar
from .config import PROGRAMS, ForecastConfig
from .inputs import Position

log = logging.getLogger(__name__)

CENT = Decimal("0.01")
TWELVE = Decimal(12)


@dataclass(frozen=True)
class CashFlow:
    account: str
    cusip: str
    program: str
    period: str
    payment_date: date
    principal: Decimal
    interest: Decimal
    projected: bool

    @property
    def total(self) -> Decimal:
        return self.principal + self.interest


def add_months(period: str, n: int) -> str:
    y, m = int(period[:4]), int(period[5:])
    idx = y * 12 + (m - 1) + n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def payment_date(program: str, period: str, cal: BusinessCalendar) -> date:
    """Investor payment date for `program` in payment month `period`."""
    rule = PROGRAMS[program]
    nominal = datetime.strptime(f"{period}-{rule.payment_day:02d}", "%Y-%m-%d")
    paid = cal.roll_forward(nominal)
    return paid.date() if isinstance(paid, datetime) else paid


def smm_from_cpr(cpr: Decimal) -> Decimal:
    # 1 - (1 - CPR) ** (1/12), with Decimal precision
    return Decimal(1) - (Decimal(1) - cpr) ** (Decimal(1) / TWELVE)


def project_factor(prior: Decimal, cpr: Decimal, sched: Decimal) -> Decimal:
    after_sched = prior * (Decimal(1) - sched)
    return (after_sched * (Decimal(1) - smm_from_cpr(cpr))).quantize(Decimal("0.00000001"))


def factor_path(pool_factors: dict[str, Decimal], first_period: str, months: int, cpr: Decimal,
                sched: Decimal) -> tuple[dict[str, Decimal], set[str]]:
    """Factors from the month before `first_period` through the horizon.

    Returns (factors, projected periods)."""
    prior_period = add_months(first_period, -1)
    if prior_period not in pool_factors:
        raise KeyError(f"no factor for {prior_period}")
    path = {prior_period: pool_factors[prior_period]}
    projected: set[str] = set()
    for i in range(months):
        p = add_months(first_period, i)
        if p in pool_factors:
            path[p] = pool_factors[p]
        else:
            path[p] = project_factor(path[add_months(p, -1)], cpr, sched)
            projected.add(p)
    return path, projected


def position_cashflows(pos: Position, pool_factors: dict[str, Decimal], first_period: str,
                       cfg: ForecastConfig, cal: BusinessCalendar) -> list[CashFlow]:
    path, projected = factor_path(pool_factors, first_period, cfg.horizon_months,
                                  cfg.cpr[pos.program], cfg.scheduled_amort)
    flows = []
    for i in range(cfg.horizon_months):
        period = add_months(first_period, i)
        prior, current = path[add_months(period, -1)], path[period]
        principal = (pos.original_face * (prior - current)).quantize(CENT, ROUND_HALF_UP)
        interest = (pos.original_face * prior * pos.coupon / TWELVE).quantize(CENT, ROUND_HALF_UP)
        if principal < 0:
            log.warning("%s %s: factor went up (%s -> %s); principal set to 0", pos.cusip, period, prior, current)
            principal = Decimal("0.00")
        flows.append(CashFlow(pos.account, pos.cusip, pos.program, period,
                              payment_date(pos.program, period, cal), principal, interest,
                              period in projected))
    return flows


def first_payment_period(as_of: date, program: str, cal: BusinessCalendar) -> str:
    """The first payment month whose payment date is on or after `as_of`."""
    period = f"{as_of.year:04d}-{as_of.month:02d}"
    if payment_date(program, period, cal) < as_of:
        period = add_months(period, 1)
    return period
