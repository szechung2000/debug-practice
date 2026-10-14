from datetime import date
from decimal import Decimal

import pytest

from mbs_cash import cashflow, inputs
from mbs_cash.calendar import BusinessCalendar, CalendarError
from mbs_cash.config import ForecastConfig
from mbs_cash.inputs import Position

CAL = BusinessCalendar({date(2026, 12, 25), date(2027, 1, 1), date(2027, 2, 15)})


def test_weekend_is_not_business_day():
    assert not CAL.is_business_day(date(2026, 12, 26))
    assert CAL.is_business_day(date(2026, 12, 24))


def test_holiday_is_not_business_day():
    assert not CAL.is_business_day(date(2026, 12, 25))


def test_roll_forward_over_weekend():
    assert CAL.roll_forward(date(2026, 12, 26)) == date(2026, 12, 28)


def test_roll_forward_outside_calendar_years():
    with pytest.raises(CalendarError):
        CAL.roll_forward(date(2030, 1, 5))


def test_payment_date_weekend_roll():
    # GNMA II pays on the 20th; 2026-12-20 is a Sunday
    assert cashflow.payment_date("GNMA_II", "2026-12", CAL) == date(2026, 12, 21)


def test_add_months():
    assert cashflow.add_months("2026-12", 1) == "2027-01"
    assert cashflow.add_months("2027-01", -1) == "2026-12"


def test_cusip_check_digit():
    assert inputs.cusip_check_digit("037833100"[:8]) == 0  # Apple Inc.


def test_principal_and_interest():
    pos = Position("A", "X", "MA1234", "GNMA_II", Decimal("0.06"), Decimal("1000000"))
    cfg = ForecastConfig(data_dir=None, output_dir=None, as_of=date(2026, 12, 18), horizon_months=1)
    flows = cashflow.position_cashflows(pos, {"2026-11": Decimal("0.50000000"), "2026-12": Decimal("0.49000000")},
                                        "2026-12", cfg, CAL)
    assert flows[0].principal == Decimal("10000.00")
    assert flows[0].interest == Decimal("2500.00")
    assert not flows[0].projected
