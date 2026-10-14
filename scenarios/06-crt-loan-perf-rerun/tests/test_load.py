from dataclasses import replace
from decimal import Decimal

import pytest

from crt_perf import loader, reader, transform
from crt_perf.config import LoadConfig

LINE = "CAS-T|L1|092026|250000.00|6.500|14|346|0|N||||N|CA\n"


def test_parse_period():
    assert reader.parse_period("092026").isoformat() == "2026-09-01"
    with pytest.raises(reader.RecordError):
        reader.parse_period("132026")


def test_parse_line():
    rec = reader.parse_line(LINE)
    assert rec["current_upb"] == Decimal("250000.00")
    assert rec["reporting_period"] == "2026-09-01"
    assert rec["zero_balance_code"] is None


def test_bad_zero_balance_code():
    with pytest.raises(reader.RecordError):
        reader.parse_line(LINE.replace("|N||||N|", "|N|0l|||N|"))


def test_dq_bucket_and_event():
    assert transform.dq_bucket("2") == "60"
    rec = reader.parse_line("CAS-T|L2|092026|0.00|6.500|14|346|6|N|09|092026|150000.00|Y|CA\n")
    out = transform.enrich(rec, Decimal("200000.00"))
    assert out["event_type"] == "CREDIT_EVENT"
    assert out["estimated_loss"] == Decimal("50000.00")


def test_chunks_cover_file(tmp_path):
    path = tmp_path / "f.txt"
    path.write_text("".join(LINE.replace("|L1|", f"|L{i}|") for i in range(23)))
    chunks = list(reader.iter_chunks(path, 5))
    assert [len(c.lines) for c in chunks] == [5, 5, 5, 5, 3]
    assert chunks[1].first_line == 6


def test_first_load_of_a_partition(tmp_path):
    cfg = replace(LoadConfig(tmp_path, tmp_path / "s.db"), chunk_size=4, workers=2)
    cfg.file_for("CAS-T", "2026-09").write_text(
        "".join(LINE.replace("|L1|", f"|L{i}|") for i in range(10)))
    result = loader.load_partition(cfg, "CAS-T", "2026-09")
    assert result.ok and result.loaded_rows == 10
    assert loader.verify_partition(cfg, "CAS-T", "2026-09")["complete"]


def test_failed_chunk_is_reported(tmp_path):
    cfg = replace(LoadConfig(tmp_path, tmp_path / "s.db"), chunk_size=4, workers=2)
    lines = [LINE.replace("|L1|", f"|L{i}|") for i in range(10)]
    lines[5] = lines[5].replace("|N||||N|", "|N|0l|||N|")
    cfg.file_for("CAS-T", "2026-09").write_text("".join(lines))
    result = loader.load_partition(cfg, "CAS-T", "2026-09")
    assert not result.ok
    assert result.failed_chunks[0][0] == 2
