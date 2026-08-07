from pathlib import Path

import pytest

from datasets.cbsl_weekly.parser import _validate_trade_identity, parse_pdf, parse_tables

FIXTURES = Path(__file__).parent / "fixtures"

SINGLE_TABLE_EDITION = "wei_20260731.pdf"  # one reserves block (full detail table caught up)
TWO_TABLE_EDITION = "wei_20260724.pdf"  # two reserves blocks (quick + lagging detailed)


def test_reserves_single_table_edition():
    result = parse_tables((FIXTURES / SINGLE_TABLE_EDITION).read_bytes())
    assert len(result["reserves"]) == 1
    block = result["reserves"][0]
    assert block["as_of"] == "June 2026"
    assert block["official_reserve_assets_usd_mn"] == 6458
    assert block["foreign_currency_reserves_usd_mn"] == 6263
    assert block["reserve_position_imf_usd_mn"] == 4
    assert block["sdrs_usd_mn"] == 1
    assert block["gold_usd_mn"] == 191
    assert block["other_reserve_assets_usd_mn"] == 0
    assert result["reserves_latest"] == block


def test_reserves_two_table_edition_not_conflated():
    result = parse_tables((FIXTURES / TWO_TABLE_EDITION).read_bytes())
    blocks = {b["as_of"]: b for b in result["reserves"]}
    assert set(blocks) == {"June 2026", "May 2026"}
    # quick "as at end June" headline table
    assert blocks["June 2026"]["official_reserve_assets_usd_mn"] == 6450
    assert blocks["June 2026"]["foreign_currency_reserves_usd_mn"] == 6254
    assert blocks["June 2026"]["gold_usd_mn"] == 191
    # lagging full-detail "as at end May" table — must not pick up June's figures
    assert blocks["May 2026"]["official_reserve_assets_usd_mn"] == 6881
    assert blocks["May 2026"]["foreign_currency_reserves_usd_mn"] == 6661
    assert blocks["May 2026"]["gold_usd_mn"] == 216
    # freshness over completeness: latest convenience value picks the newer "as_of"
    assert result["reserves_latest"]["as_of"] == "June 2026"
    assert result["reserves_latest"]["official_reserve_assets_usd_mn"] == 6450


def test_external_trade_exact_figures():
    result = parse_tables((FIXTURES / SINGLE_TABLE_EDITION).read_bytes())
    trade = result["trade"]
    assert trade["period"] == "Jan - June"
    assert trade["exports"]["usd_mn"] == {"2025": 6492.1, "2026": 6903.0}
    assert trade["imports"]["usd_mn"] == {"2025": 9762.2, "2026": 12392.3}
    # Trade Balance row: last two figures run together with no space in the source
    # text ("(973,901.7)(1,746,178.3)") — confirms that case is handled.
    assert trade["trade_balance"]["usd_mn"] == {"2025": -3270.1, "2026": -5489.3}
    assert trade["trade_balance"]["rs_mn"] == {"2025": -973901.7, "2026": -1746178.3}
    breakdown = {r["label"]: r for r in trade["exports_breakdown"]}
    assert breakdown["Textiles and Garments"]["usd_mn"]["2026"] == 2451.0
    # "Unclassified" appears once under exports and once under imports with
    # different values — must not collide since each is scoped to its own list.
    imports_breakdown = {r["label"]: r for r in trade["imports_breakdown"]}
    assert breakdown["Unclassified"]["usd_mn"]["2026"] == 10.1
    assert imports_breakdown["Unclassified"]["usd_mn"]["2026"] == 13.1


def test_trade_balance_identity_holds_on_real_data():
    result = parse_tables((FIXTURES / SINGLE_TABLE_EDITION).read_bytes())
    trade = result["trade"]
    assert trade["exports"]["usd_mn"]["2026"] - trade["imports"]["usd_mn"]["2026"] == pytest.approx(-5489.3)
    _validate_trade_identity(trade)  # must not raise


def test_trade_balance_identity_raises_on_broken_data():
    good = parse_tables((FIXTURES / SINGLE_TABLE_EDITION).read_bytes())["trade"]
    broken = dict(good)
    broken["trade_balance"] = {
        "usd_mn": {"2025": good["trade_balance"]["usd_mn"]["2025"], "2026": -1234.0},  # deliberately wrong
        "rs_mn": good["trade_balance"]["rs_mn"],
    }
    with pytest.raises(ValueError, match="trade balance identity failed"):
        _validate_trade_identity(broken)


def test_trade_indices():
    result = parse_tables((FIXTURES / SINGLE_TABLE_EDITION).read_bytes())
    indices = result["trade_indices"]
    assert indices["total_exports"]["value"] == {"year_ago": 158.9, "month_ago": 170.4, "latest": 159.2}
    assert indices["total_exports"]["quantity"]["latest"] == 176.6
    assert indices["total_imports"]["unit_value"]["latest"] == 96.7
    assert indices["terms_of_trade"] == {"year_ago": 94.9, "month_ago": 72.8, "latest": 93.3}


def test_commodity_prices_best_effort():
    result = parse_tables((FIXTURES / SINGLE_TABLE_EDITION).read_bytes())
    commodities = result["commodity_prices"]
    tea = commodities["tea_per_kg"]
    assert tea["usd_2025"] == 3.71 and tea["usd_2026"] == 3.50
    assert tea["usd_pct_change"] == -5.7
    assert tea["lkr_2025"] == 1113.82 and tea["lkr_2026"] == 1169.94
    assert commodities["rice_per_mt"]["usd_2026"] == 799.99
    # Crude Oil is explicitly skipped — its figures are garbled in the source text
    assert "crude_oil_per_barrel" not in commodities


def test_parse_pdf_merges_tables_additively():
    # The prose-regex path (existing contract) must keep working on an edition that
    # has the reserves/exports prose paragraphs, with tables merged in additively.
    result = parse_pdf((FIXTURES / SINGLE_TABLE_EDITION).read_bytes())
    assert "reserves_usd_mn" in result or "exports_usd_mn" in result  # prose fields intact
    assert "_tables_error" not in result, result.get("_tables_error")
    assert result["tables"]["reserves"]
    assert result["tables"]["trade"]["trade_balance"]


def test_parse_pdf_falls_back_to_tables_on_mid_month_edition():
    # Ground truth: wei_20260724.pdf is a mid-month edition that lacks the
    # reserves/exports prose paragraphs entirely (root cause the plan called out —
    # only rupee-YTD prose survives mid-month). parse_pdf must not raise here: table
    # extraction is exactly the fallback this task exists to provide.
    result = parse_pdf((FIXTURES / TWO_TABLE_EDITION).read_bytes())
    assert "reserves_usd_mn" not in result and "exports_usd_mn" not in result
    assert "_tables_error" not in result, result.get("_tables_error")
    assert result["tables"]["reserves"]
    assert result["tables"]["trade"]["trade_balance"]
