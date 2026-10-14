from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from cmbs_ingest import transform
from cmbs_ingest.parser import LoanPeriodic, ParseError, parse_amount, parse_date, parse_rate


def make(loan_id="L1", received_at="12/17/2025 09:00:00", source="D-1_202512_LPU.csv", end="100.00"):
    return LoanPeriodic(
        deal_id="D-1", loan_id=loan_id, period="202512",
        distribution_date=date(2025, 12, 17), determination_date=date(2025, 12, 11),
        beginning_balance=Decimal("100.00"), scheduled_principal=Decimal("0"),
        unscheduled_principal=Decimal("100.00") - Decimal(end), ending_balance=Decimal(end),
        current_rate=Decimal("0.05"), paid_through_date=None, delinquency_status="0",
        servicer_comment="", source_file=source, servicer="MIDLAND", received_at=received_at,
    )


@pytest.mark.parametrize("raw,expected", [
    ("1,234.56", Decimal("1234.56")),
    ("$1,234.56", Decimal("1234.56")),
    ("(12.50)", Decimal("-12.50")),
    ("", Decimal("0")),
    ("N/A", Decimal("0")),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


def test_parse_amount_rejects_garbage():
    with pytest.raises(ParseError):
        parse_amount("12..5")


def test_parse_rate_accepts_percent_and_decimal():
    assert parse_rate("5.25") == Decimal("0.0525")
    assert parse_rate("0.0525") == Decimal("0.0525")


def test_parse_date_formats():
    assert parse_date("20251211") == date(2025, 12, 11)
    assert parse_date("2025-12-11") == date(2025, 12, 11)
    assert parse_date("12/11/2025") == date(2025, 12, 11)


def test_restatement_replaces_original_same_day():
    original = make(received_at="12/17/2025 09:00:00", end="100.00")
    restated = make(received_at="12/17/2025 15:30:00", source="D-1_202512_LPU_R1.csv", end="90.00")
    rows = transform.select_latest_versions([restated, original], transform.TransformStats())
    assert len(rows) == 1
    assert rows[0].ending_balance == Decimal("90.00")


def test_partial_restatement_keeps_other_loans():
    original = [make("L1"), make("L2")]
    restated = make("L2", received_at="12/19/2025 10:00:00", source="D-1_202512_LPU_R1.csv", end="80.00")
    rows = transform.select_latest_versions(original + [restated], transform.TransformStats())
    by_loan = {r.loan_id: r for r in rows}
    assert by_loan["L1"].ending_balance == Decimal("100.00")
    assert by_loan["L2"].ending_balance == Decimal("80.00")


def test_pipeline_runs_end_to_end(tmp_path):
    from cmbs_ingest.cli import main
    landing = Path(__file__).resolve().parents[1] / "data" / "landing"
    if not landing.exists():
        pytest.skip("run python data/generate.py first")
    rc = main(["run", "--landing", str(landing), "--warehouse", str(tmp_path / "w.db"), "--period", "202510"])
    assert rc == 0
