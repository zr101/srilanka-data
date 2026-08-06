from pathlib import Path

import pytest

from datasets.cbsl_daily.parser import parse_pdf

FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_known_edition_exactly():
    result = parse_pdf((FIXTURES / "cbsl_daily_20260805.pdf").read_bytes())
    # Cross-checked against the Treasury auction press release of 05.08.2026
    assert result["tbill"] == {"d91": 9.77, "d182": 9.99, "d364": 10.19}
    assert result["opr"] == 8.75
    assert result["srr"] == 2.00
    assert result["awpr"] == 10.67
    assert result["tbill_secondary"]["d364"] is not None


@pytest.mark.parametrize("name", sorted(p.name for p in FIXTURES.glob("cbsl_daily_*.pdf")))
def test_all_snapshot_editions_parse_plausibly(name):
    result = parse_pdf((FIXTURES / name).read_bytes())
    for tenor in ("d91", "d182", "d364"):
        assert result["tbill"][tenor] is not None
        assert 0 < result["tbill"][tenor] < 50
    assert result["opr"] is not None
    # yield curve sanity: longer tenor >= shorter, loosely
    assert result["tbill"]["d364"] >= result["tbill"]["d91"] - 0.5


def test_rejects_non_template_pdf():
    with pytest.raises(Exception):
        parse_pdf(b"%PDF-1.4 not really a report")
