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


def test_full_panels_on_known_edition():
    from datasets.cbsl_daily.parser import parse_pdf

    result = parse_pdf((FIXTURES / "cbsl_daily_20260805.pdf").read_bytes())
    assert result["ncpi_yoy_pct"] == 6.5 and result["ccpi_yoy_pct"] == 7.3
    assert result["fx_tt"]["usd"]["tt_sell"] == 340.1378
    assert result["usd_spot"] == 335.73
    assert result["pump_prices_rs"]["petrol92"] == 414.0  # cross-checks ceypetco
    assert result["crude_usd"]["brent"] == 79.94
    mix = result["electricity"]["generation_mix_pct"]
    assert abs(sum(mix.values()) - 100) < 0.6
    assert result["share_market"]["pe_ratio"] == 11.18


import pytest as _pytest


@_pytest.mark.parametrize("name", sorted(p.name for p in FIXTURES.glob("cbsl_daily_*.pdf")))
def test_panels_parse_all_editions(name):
    from datasets.cbsl_daily.parser import parse_pdf

    result = parse_pdf((FIXTURES / name).read_bytes())
    assert "_panels_error" not in result, result.get("_panels_error")
    assert result.get("fx_tt", {}).get("usd")
    assert result.get("electricity", {}).get("generation_mix_pct")
