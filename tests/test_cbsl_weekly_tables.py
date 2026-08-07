import io
from pathlib import Path

import pytest
from pypdf import PdfWriter

from datasets.cbsl_weekly import parser as wp
from datasets.cbsl_weekly.parser import _parse_reserves, _validate_trade_identity, parse_pdf, parse_tables

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


def test_reserves_window_clipped_at_next_caption():
    # Direct unit test on the pure function: a field missing from the nearer
    # (June) block must come back missing, never silently backfilled from the
    # farther (May) block just because the fixed-size window used to overreach
    # into it. Real editions could plausibly omit a zero row like this.
    lines = [
        "4.3 Official Reserve Assets as at end June 2026 (USD Mn)",
        "Official Reserve Assets(b) 6,450",
        "Foreign Currency Reserves 6,254",
        "Reserve position in the IMF 4",
        "SDRs 1",
        "Gold 191",
        # June block deliberately omits "Other Reserve Assets" here.
        "4.4 International Reserves & Foreign Currency Liquidity as at end May 2026(a)",
        "(USD Mn)",
        "Official Reserve Assets(b) 6,881",
        "Foreign Currency Reserves 6,661",
        "Reserve position in the IMF 4",
        "SDRs 1",
        "Gold 216",
        "Other Reserve Assets 0",
    ]
    blocks = {b["as_of"]: b for b in _parse_reserves(lines)}
    assert "other_reserve_assets_usd_mn" not in blocks["June 2026"]
    assert blocks["May 2026"]["other_reserve_assets_usd_mn"] == 0
    # sanity: fields both blocks do have still resolve to their own, distinct values
    assert blocks["June 2026"]["gold_usd_mn"] == 191
    assert blocks["May 2026"]["gold_usd_mn"] == 216


def test_trade_group_failure_does_not_wipe_out_other_groups(monkeypatch):
    # A trade-identity failure must only cost the trade group — reserves/trade_indices/
    # commodity_prices that already parsed fine earlier in the same parse_tables()
    # call must survive, and parse_pdf must not regress to its old unconditional
    # raise on a mid-month (no-prose) edition just because trade specifically broke.
    real_parse_trade = wp._parse_trade

    def broken_parse_trade(lines):
        trade = real_parse_trade(lines)
        if trade:
            trade = dict(trade)
            trade["trade_balance"] = {
                "usd_mn": {**trade["trade_balance"]["usd_mn"], "2026": -1234.0},  # deliberately wrong
                "rs_mn": trade["trade_balance"]["rs_mn"],
            }
        return trade

    monkeypatch.setattr(wp, "_parse_trade", broken_parse_trade)

    tables = wp.parse_tables((FIXTURES / TWO_TABLE_EDITION).read_bytes())
    assert "trade" not in tables
    assert "trade balance identity failed" in tables["_group_errors"]["trade"]
    assert tables["reserves"]
    assert tables["trade_indices"]
    assert tables["commodity_prices"]

    result = wp.parse_pdf((FIXTURES / TWO_TABLE_EDITION).read_bytes())
    assert "_tables_error" not in result, result.get("_tables_error")
    assert result["tables"]["reserves"]  # did not fall back to the old unconditional raise


def test_parse_tables_raises_cleanly_on_blank_pdf():
    # Regression guard: a structurally valid but content-free PDF must still raise
    # (not silently return {}) so a future refactor can't reintroduce an
    # "empty results pass through" bug with nothing to catch it.
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    with pytest.raises(ValueError, match="no tables recognized"):
        parse_tables(buf.getvalue())


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


def test_price_indices_ncpi_headline_and_core():
    # 2026-07-31 edition: NCPI lags one month behind the bulletin date ("June May
    # June" — year-ago June-2025, month-ago May-2026, latest June-2026).
    result = parse_tables((FIXTURES / SINGLE_TABLE_EDITION).read_bytes())
    ncpi = result["price_indices"]["ncpi"]
    assert ncpi["months"] == {"year_ago": "June 2025", "month_ago": "May 2026", "latest": "June 2026"}
    assert ncpi["headline"]["index"] == {"year_ago": 208.7, "month_ago": 218.8, "latest": 222.3}
    assert ncpi["headline"]["monthly_change_pct"] == {"year_ago": 0.6, "month_ago": 1.2, "latest": 1.6}
    # Parenthesized negative must parse as a real negative number.
    assert ncpi["headline"]["annual_avg_change_pct"] == {"year_ago": -0.9, "month_ago": 2.4, "latest": 2.9}
    assert ncpi["headline"]["yoy_change_pct"] == {"year_ago": 0.3, "month_ago": 5.4, "latest": 6.5}
    # Core has no "Monthly Change %" row at all — asymmetric with Headline, not a
    # missing/zero value.
    assert ncpi["core"]["index"] == {"year_ago": 194.8, "month_ago": 203.0, "latest": 204.6}
    assert "monthly_change_pct" not in ncpi["core"]
    assert ncpi["core"]["annual_avg_change_pct"] == {"year_ago": 0.9, "month_ago": 2.3, "latest": 2.7}
    assert ncpi["core"]["yoy_change_pct"] == {"year_ago": 0.6, "month_ago": 4.5, "latest": 5.0}


def test_price_indices_ccpi_headline_and_core():
    # Same edition, CCPI block: current-month reporting ("July June July"), one
    # month ahead of NCPI's own lag — confirms the two blocks' month labels are
    # read independently rather than assumed to match.
    result = parse_tables((FIXTURES / SINGLE_TABLE_EDITION).read_bytes())
    ccpi = result["price_indices"]["ccpi"]
    assert ccpi["months"] == {"year_ago": "July 2025", "month_ago": "June 2026", "latest": "July 2026"}
    assert ccpi["headline"]["index"] == {"year_ago": 194.1, "month_ago": 207.7, "latest": 208.2}
    assert ccpi["headline"]["monthly_change_pct"] == {"year_ago": -0.2, "month_ago": 2.1, "latest": 0.2}
    assert ccpi["headline"]["annual_avg_change_pct"] == {"year_ago": -1.6, "month_ago": 2.7, "latest": 3.3}
    assert ccpi["headline"]["yoy_change_pct"] == {"year_ago": -0.3, "month_ago": 6.8, "latest": 7.3}
    assert ccpi["core"]["index"] == {"year_ago": 180.8, "month_ago": 187.3, "latest": 188.8}
    assert "monthly_change_pct" not in ccpi["core"]
    assert ccpi["core"]["annual_avg_change_pct"] == {"year_ago": 1.9, "month_ago": 2.6, "latest": 2.9}
    assert ccpi["core"]["yoy_change_pct"] == {"year_ago": 1.6, "month_ago": 4.0, "latest": 4.4}


def test_price_indices_ccpi_headline_yoy_matches_prose_anchor():
    # Ground truth: this edition's own "Highlights of the Week" prose says CCPI
    # headline inflation "increased to 7.3 per cent in July 2026 from 6.8 per cent
    # in June 2026" — the parsed month-ago/latest YoY figures must match exactly.
    result = parse_tables((FIXTURES / SINGLE_TABLE_EDITION).read_bytes())
    yoy = result["price_indices"]["ccpi"]["headline"]["yoy_change_pct"]
    assert yoy["month_ago"] == 6.8
    assert yoy["latest"] == 7.3


def test_price_indices_different_edition_shifted_months():
    # 2026-07-24 edition (TWO_TABLE_EDITION fixture): CCPI here reports "June May
    # June" rather than "July June July" — confirms month labels shift edition to
    # edition and are read fresh each time, not hardcoded/cached from another parse.
    result = parse_tables((FIXTURES / TWO_TABLE_EDITION).read_bytes())
    ccpi = result["price_indices"]["ccpi"]
    assert ccpi["months"] == {"year_ago": "June 2025", "month_ago": "May 2026", "latest": "June 2026"}
    assert ccpi["headline"]["yoy_change_pct"] == {"year_ago": -0.6, "month_ago": 5.5, "latest": 6.8}
    assert ccpi["core"]["yoy_change_pct"] == {"year_ago": 1.5, "month_ago": 3.9, "latest": 4.0}


def test_price_indices_does_not_bleed_into_1_2_prices():
    # "1.2 Prices" (Pettah/Marandagahamula/... market tables) is explicitly out of
    # scope for this table — confirm it isn't accidentally captured as extra data.
    result = parse_tables((FIXTURES / SINGLE_TABLE_EDITION).read_bytes())
    price_indices = result["price_indices"]
    assert set(price_indices) == {"ncpi", "ccpi"}
    assert set(price_indices["ncpi"]) == {"months", "headline", "core"}


def test_price_indices_ncpi_scan_does_not_bleed_into_ccpi_block():
    # Direct unit test on the pure function: if a future edition ever dropped an
    # entire Core sub-block (not just its already-observed missing "Monthly
    # Change %" row), NCPI's forward scan must be hard-clipped at CCPI's own
    # caption line — not rely on "keep scanning until headline+core both seen"
    # — otherwise it would run on into CCPI's own "...(CCPI) - Headline..." line
    # (which also contains "- Headline") and silently overwrite NCPI's entry with
    # CCPI's data instead of correctly coming back incomplete.
    lines = [
        "1.1 Price Indices",
        "2025 2026",
        "NCPI (2021=100)",
        "June May June",
        "National Consumer Price Index (NCPI) - Headline 208.7 218.8 222.3",
        "Monthly Change % 0.6 1.2 1.6",
        "Annual Average Change % (0.9) 2.4 2.9",
        "Year-on-Year Change % 0.3 5.4 6.5",
        # NCPI Core sub-block deliberately omitted entirely here.
        "2025 2026",
        "CCPI - Year-on-Year %",
        "CCPI (2021=100)",
        "July June July",
        "Colombo Consumer Price Index (CCPI) - Headline 194.1 207.7 208.2",
        "Monthly Change % (0.2) 2.1 0.2",
        "Annual Average Change % (1.6) 2.7 3.3",
        "Year-on-Year Change % (0.3) 6.8 7.3",
        "Colombo Consumer Price Index (CCPI) - Core 180.8 187.3 188.8",
        "Annual Average Change % 1.9 2.6 2.9",
        "Year-on-Year Change % 1.6 4.0 4.4",
        "Source: Department of Census and Statistics",
        "1.2 Prices",
    ]
    result = wp._parse_price_indices(lines)
    # NCPI is genuinely incomplete (no Core) — must come back missing, not silently
    # backfilled with CCPI's Headline/Core mislabeled as its own.
    assert "ncpi" not in result
    # CCPI must still parse correctly and untouched by NCPI's failed scan.
    assert result["ccpi"]["headline"]["index"] == {"year_ago": 194.1, "month_ago": 207.7, "latest": 208.2}
    assert result["ccpi"]["core"]["index"] == {"year_ago": 180.8, "month_ago": 187.3, "latest": 188.8}


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
