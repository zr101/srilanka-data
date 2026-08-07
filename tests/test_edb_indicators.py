import io
from pathlib import Path

import pytest
from pypdf import PdfReader

from datasets.edb_indicators.parser import (
    _parse_entity_page,
    find_table_text,
    parse_countries,
    parse_pdf,
    parse_products,
    parse_table13,
    parse_table15,
    parse_table17,
    parse_text,
    parse_toc,
)

FIXTURES = Path(__file__).parent / "fixtures"

# edb_2024.pdf / edb_2023.pdf are trimmed from the real ~340-page, ~3-22MB EDB ebooks
# down to 172/~70 pages, ~900KB/~265KB. Trimming is BLANK-IN-PLACE, not truncation: every
# page from index 0 up to the last one we need (171 for edb_2024.pdf, to reach the
# 24.*/25.* fixture pages below) is kept in the writer, with only the pages our parsers
# don't touch (front matter, graphs, tables outside 1/13/15/17/24.*/25.*/the TOC-map
# generalization check) replaced by a same-size blank page rather than removed. This
# preserves the pypdf page index of every kept page exactly as it is in the original
# document — which matters because parse_toc() derives its TOC-number -> pypdf-index
# offset from an anchor page's ACTUAL position (see its docstring). Naively
# dropping/reordering pages would shift that position and silently produce a wrong
# offset that still "works" (resolves to SOME page) but points at the wrong content.
# See datasets/edb_indicators/parser.py's TOC section comment for the offset
# derivation itself. If you add a 3rd/4th edition fixture, rebuild it the same way
# (pypdf.PdfWriter, add_blank_page for anything before your last needed page index,
# add_page for the rest) rather than slicing pages out.
EDB_2024 = "edb_2024.pdf"  # 6 year columns (2019-2024) — the previously-working case
EDB_2023 = "edb_2023.pdf"  # 5 year columns (2019-2023) — the edition that used to be silently skipped

# 24.*/25.* fixture pages un-blanked in edb_2024.pdf (indices verified directly against
# the live source PDF, not just transcribed): a short country with no "Other Products"
# bucket (Albania), a large capped country with one (China), a large capped product with
# an "Other Markets" bucket (Tea), and a capped-but-sparse product exercising "-" in
# every column type (Green Tea).
ALBANIA_PAGE = 66  # Table 24.01, unit = Thousands, Total row numbered "26 Total :"
CHINA_PAGE = 81  # Table 24.16, unit = Millions, Total row unnumbered "Total :"
TEA_PAGE = 167  # Table 25.01, header "No Market" (25.* rows are markets, not products)
GREEN_TEA_PAGE = 171  # Table 25.05


def test_toc_resolves_required_tables():
    toc = parse_toc((FIXTURES / EDB_2024).read_bytes())
    assert toc["1"] == 10
    assert toc["13"] == 25
    assert toc["17"] == 35
    # not in scope to parse, but the map should generalize beyond 1/13/17 since it's
    # built in full (cheap once TOC pages are being parsed at all)
    assert toc["21.01"] == 43
    assert toc["24.01"] == 66


def test_toc_offset_not_hardcoded_across_editions():
    # Both fixtures happen to share a +9 offset, but parse_toc must derive it from
    # the anchor page rather than assume it — this only proves the derivation lands
    # on the same (correct) answer for both, not that +9 is baked in.
    toc_2024 = parse_toc((FIXTURES / EDB_2024).read_bytes())
    toc_2023 = parse_toc((FIXTURES / EDB_2023).read_bytes())
    assert toc_2024["13"] == toc_2023["13"] == 25
    assert toc_2024["17"] == toc_2023["17"] == 35


def test_table1_six_year_edition_unregressed():
    result = parse_text(find_table_text((FIXTURES / EDB_2024).read_bytes()))
    assert result["years"] == [2019, 2020, 2021, 2022, 2023, 2024]
    assert result["total_usd_mn"] == [15828, 12335, 14429, 14995, 15106, 16344]
    assert len(result["merchandise_usd_mn"]) == 6


def test_table1_five_year_edition_no_longer_skipped():
    # Ground truth: the 2023 edition's Table 1 page has only 5 year columns
    # (2019-2023) — this used to raise "EDB years header incomplete" and get the
    # whole edition silently skipped by the scraper.
    result = parse_text(find_table_text((FIXTURES / EDB_2023).read_bytes()))
    assert result["years"] == [2019, 2020, 2021, 2022, 2023]
    assert result["total_usd_mn"] == [15828, 12335, 14429, 14995, 15106]
    assert len(result["services_usd_mn"]) == 5


def test_table13_tea_and_rubber_rows_2024():
    result = parse_table13((FIXTURES / EDB_2024).read_bytes())
    assert result["years"] == [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]
    by_desc = {r["description"]: r for r in result["rows"]}
    tea = by_desc["Tea"]
    assert tea["values"]["2016"] == 1269.03
    assert tea["values"]["2024"] == 1435.87
    assert tea["avg_growth_pct"] == 9.62
    # regression guard for the embedded-space artifact ("649. 67" -> 649.67)
    assert by_desc["Tea Packets"]["values"]["2023"] == 649.67
    # regression guard for a two-sided split artifact ("58 4.05" -> 584.05)
    assert by_desc["Tea in Bulk"]["values"]["2023"] == 584.05
    # regression guard for a trailing-digit split artifact ("27.1 1" -> 27.11)
    assert by_desc["Instant Tea"]["values"]["2024"] == 27.11
    rubber = by_desc["Rubber & Rubber Based Products"]
    assert rubber["values"]["2016"] == 800.56
    assert rubber["avg_growth_pct"] == 7.66


def test_table13_grand_total_row_2024():
    result = parse_table13((FIXTURES / EDB_2024).read_bytes())
    total = result["total"]
    assert total["values"]["2016"] == 10219.9
    assert total["values"]["2024"] == 12771.63
    assert total["avg_growth_pct"] == 7.23
    # "Total" itself must not also show up in the flat row list
    assert "Total" not in {r["description"] for r in result["rows"]}
    assert len(result["rows"]) > 100  # ~257 real product lines


def test_table13_five_year_edition_dash_prefixed_subitems():
    # Ground truth: the 2023 edition marks sub-items with a leading '-'/'--' and
    # uses '...' rather than '-' as its placeholder token — both editions must
    # still resolve to the same clean (dash-stripped) description text.
    result = parse_table13((FIXTURES / EDB_2023).read_bytes())
    assert result["years"] == [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023]
    by_desc = {r["description"]: r for r in result["rows"]}
    assert "Tea Packets" in by_desc  # leading '-' stripped, not left as "-Tea Packets"
    assert by_desc["Tea Packets"]["values"]["2023"] == 649.67
    assert result["total"]["values"]["2023"] == 11631.09


def test_table15_total_exports_row_2024():
    result = parse_table15((FIXTURES / EDB_2024).read_bytes())
    assert result["bands"] == ["total", "over_100", "100_to_50", "50_to_35", "35_to_1", "1_to_0"]
    assert len(result["sectors"]) == 11  # 10 sectors + Total Exports
    total = next(s for s in result["sectors"] if s["sector"] == "Total Exports")
    assert total["by_band"]["total"] == {"exporters": 4335, "turnover_usd_mn": 12023.93}
    assert total["by_band"]["over_100"] == {"exporters": 17, "turnover_usd_mn": 3704.43}
    assert total["by_band"]["100_to_50"] == {"exporters": 26, "turnover_usd_mn": 1608.38}
    # "50 to >35" turnover is missing its thousands-comma in the source ("1472.37" not
    # "1,472.37") — must still parse as 1472.37, not truncate/misparse.
    assert total["by_band"]["50_to_35"] == {"exporters": 35, "turnover_usd_mn": 1472.37}
    assert total["by_band"]["35_to_1"] == {"exporters": 749, "turnover_usd_mn": 4757.85}
    assert total["by_band"]["1_to_0"] == {"exporters": 3508, "turnover_usd_mn": 480.89}


def test_table15_dash_sentinel_means_zero_not_dropped_2024():
    result = parse_table15((FIXTURES / EDB_2024).read_bytes())
    by_sector = {s["sector"]: s for s in result["sectors"]}
    # Coconut & Coconut Based Products has "- -" for the "Over 100" band in the source
    # — zero exporters/turnover in that band, not missing data.
    assert by_sector["Coconut & Coconut Based Products"]["by_band"]["over_100"] == {
        "exporters": 0,
        "turnover_usd_mn": 0.0,
    }


def test_table15_multiline_sector_labels_joined_2024():
    result = parse_table15((FIXTURES / EDB_2024).read_bytes())
    by_sector = {s["sector"]: s for s in result["sectors"]}
    # These sector names wrap across 2-3 lines in the source PDF text extraction;
    # must join into a single clean label, not arrive fragmented.
    assert "Rubber & Rubber Based Products" in by_sector
    assert by_sector["Rubber & Rubber Based Products"]["by_band"]["total"] == {
        "exporters": 280,
        "turnover_usd_mn": 1001.54,
    }
    assert "Diamonds, Gems & Jewellery" in by_sector
    assert by_sector["Diamonds, Gems & Jewellery"]["by_band"]["over_100"] == {
        "exporters": 1,
        "turnover_usd_mn": 131.05,
    }
    assert "Coconut & Coconut Based Products" in by_sector
    assert "Electrical & Electronic Components" in by_sector
    assert "Food & Beverages" in by_sector
    assert "Spices & Concentrates" in by_sector
    # "Plasitc" is a typo in the source document itself — preserved verbatim, not
    # silently corrected to "Plastic".
    assert "Chemical & Plasitc Products" in by_sector


def test_table15_five_year_edition():
    # Ground truth: the 2023 edition's Table 15 page — same 11-row/6-band shape as
    # 2024, and the band label line's layout differs (split across two reversed
    # lines rather than one), which is exactly what the parser's hardcoded band
    # order (see parser.py's Table 15 banner comment) is there to be robust against.
    result = parse_table15((FIXTURES / EDB_2023).read_bytes())
    assert len(result["sectors"]) == 11  # exercises TABLE15_EXPECTED_ROWS on real data
    total = next(s for s in result["sectors"] if s["sector"] == "Total Exports")
    assert total["by_band"]["total"] == {"exporters": 4426, "turnover_usd_mn": 11631.05}
    assert total["by_band"]["35_to_1"] == {"exporters": 769, "turnover_usd_mn": 4921.41}
    by_sector = {s["sector"]: s for s in result["sectors"]}
    # Sector label not wrapped in this edition's layout (unlike 2024) — must still parse.
    assert by_sector["Rubber & Rubber Based Products"]["by_band"]["total"] == {
        "exporters": 265,
        "turnover_usd_mn": 930.23,
    }
    # "-" sentinel still resolves to 0 in this edition too.
    assert by_sector["Coconut & Coconut Based Products"]["by_band"]["over_100"] == {
        "exporters": 0,
        "turnover_usd_mn": 0.0,
    }


def test_table17_exact_line_items_and_totals_2024():
    result = parse_table17((FIXTURES / EDB_2024).read_bytes())
    assert result["goods"]["Apparel & Textiles"] == 5282
    assert result["goods"]["Tea"] == 1484
    assert result["goods"]["Others"] == 1944
    assert result["goods"]["total"] == 14098
    assert result["services"]["ICT/ BPM"] == 1711
    # source typo "1.978" for Transport & Logistics must resolve to 1978, not 1.978
    assert result["services"]["Transport & Logistics"] == 1978
    assert result["services"]["total"] == 4191
    assert result["grand_total"] == 18289


def test_table17_five_year_edition():
    result = parse_table17((FIXTURES / EDB_2023).read_bytes())
    assert result["goods"]["total"] == 12752
    assert result["services"]["total"] == 3652
    assert result["grand_total"] == 16404


def test_parse_pdf_merges_tables_additively():
    result = parse_pdf((FIXTURES / EDB_2024).read_bytes())
    assert result["total_usd_mn"] == [15828, 12335, 14429, 14995, 15106, 16344]  # core contract intact
    assert "_table13_error" not in result, result.get("_table13_error")
    assert "_table15_error" not in result, result.get("_table15_error")
    assert "_table17_error" not in result, result.get("_table17_error")
    assert result["table13"]["total"]["values"]["2024"] == 12771.63
    assert result["table15"]["sectors"][0]["by_band"]["total"]["exporters"] == 4335
    assert result["table17"]["grand_total"] == 18289


# --- Table 24.*/25.*: Exports by Market x Product -----------------------------------


def _pages(edition=EDB_2024):
    return PdfReader(io.BytesIO((FIXTURES / edition).read_bytes())).pages


def test_entity_page_albania_numbered_total_and_thousands_unit():
    # Ground truth: Albania (24.01) is a short, uncapped list — no "Other Products"
    # bucket — and its "Total :" row continues the row numbering ("26 Total :").
    # Unit is already USD Thousands, so values must come through unscaled.
    page = _parse_entity_page(_pages(), ALBANIA_PAGE, "Product", table_id="24.01")
    assert page["entity"] == "ALBANIA"
    assert page["years"] == [2020, 2021, 2022, 2023, 2024]
    assert page["unit"] == "USD Thousands"
    assert page["other"] is None
    assert page["total"] == {
        "no": 26,
        "name": "Total",
        "values_usd": {"2020": 6723.42, "2021": 8004.99, "2022": 6356.35, "2023": 5466.47, "2024": 9235.89},
        "share_pct": 100.0,
        "avg_growth_pct": 2.54,
    }
    assert page["merchandise_share_pct"] == {"2020": 0.067, "2021": 0.064, "2022": 0.048, "2023": 0.046, "2024": 0.072}
    by_no = {r["no"]: r for r in page["rows"]}
    assert by_no[1]["name"] == "Tea Packets"
    assert by_no[1]["values_usd"]["2024"] == 6433.87
    # row 6's name ("Coco Peat, Fiber Pith & Moulded products") wraps its row number
    # onto its own line in the source text — must still resolve to row 6, not get lost.
    assert by_no[6]["name"] == "Coco Peat, Fiber Pith & Moulded products"
    assert by_no[6]["values_usd"]["2022"] == 10.0
    # row 12 ("Petroleum Oils") is missing one of its 7 expected value tokens in the
    # source itself (a genuine artifact, verified directly against the live PDF) —
    # unrecoverable, must be skipped rather than corrupting every row after it.
    assert 12 not in by_no
    assert by_no[13]["name"] == "Miscellaneous Edible Preparations"  # the row right after the dropped one


def test_entity_page_china_unnumbered_total_and_other_bucket_and_millions_unit():
    # Ground truth: China (24.16) is a capped 40-row list with an "Other Products"
    # catch-all, and its "Total :" row is NOT numbered (unlike Albania's). Unit is
    # Millions and must be normalized to Thousands (x1000) in the output.
    page = _parse_entity_page(_pages(), CHINA_PAGE, "Product", table_id="24.16")
    assert page["entity"] == "CHINA"
    assert page["unit"] == "USD Thousands"
    assert len(page["rows"]) == 40
    assert page["total"]["no"] is None
    assert page["total"]["values_usd"]["2024"] == 251910.0  # 251.91 Mn -> 251910.0 Th
    assert page["other"] is not None
    assert page["other"]["name"] == "Other Products"
    assert page["other"]["values_usd"] == {
        "2020": 20760.0,
        "2021": 35170.0,
        "2022": 19110.0,
        "2023": 29150.0,
        "2024": 14240.0,
    }
    assert page["other"]["share_pct"] == 5.65
    assert page["other"]["avg_growth_pct"] == -9.42
    # row 35's name wraps across 3 lines in the source (number attached to line 1 this
    # time, unlike Albania's row 6/17) — must still join into one clean name.
    by_no = {r["no"]: r for r in page["rows"]}
    assert by_no[35]["name"] == "Made-up Textile Articles (Blankets, Rugs, Linen, Curtains etc)"
    assert by_no[35]["values_usd"]["2024"] == 1080.0  # 1.08 Mn -> 1080.0 Th


def test_entity_page_tea_other_markets_bucket_and_market_header():
    # Ground truth: Tea (25.01) is a product page, so its rows are destination markets
    # ("No Market" header, not "No Product") and its own entity caption is "Product :".
    page = _parse_entity_page(_pages(), TEA_PAGE, "Market", table_id="25.01")
    assert page["entity"] == "TEA (Tea Packets, Tea Bags, Tea in Bulk, Instant Tea & Green Tea etc.)"
    assert page["other"]["name"] == "Other Markets"
    assert page["other"]["values_usd"]["2024"] == 94680.0  # 94.68 Mn -> 94680.0 Th
    assert page["total"]["values_usd"]["2024"] == 1435860.0  # 1435.86 Mn -> 1435860.0 Th
    by_no = {r["no"]: r for r in page["rows"]}
    assert by_no[1]["name"] == "Iraq"
    assert by_no[1]["values_usd"]["2024"] == 151560.0  # 151.56 Mn -> 151560.0 Th


def test_entity_page_green_tea_dash_sentinel_semantics():
    # Ground truth: Green Tea (25.05) is capped-but-sparse — good coverage of the "-"
    # sentinel in every column type. Per the source's own footnote, "-" means zero in a
    # value/share column but "insignificant/not computable" (-> None) in % Avg. Growth.
    page = _parse_entity_page(_pages(), GREEN_TEA_PAGE, "Market", table_id="25.05")
    by_name = {r["name"]: r for r in page["rows"]}

    # Albania (row 8): "- - - - 0.10 1.76 -" — leading years are real zeros, growth "-" is null.
    albania = by_name["Albania"]
    assert albania["no"] == 8
    assert albania["values_usd"] == {"2020": 0.0, "2021": 0.0, "2022": 0.0, "2023": 0.0, "2024": 100.0}
    assert albania["share_pct"] == 1.76
    assert albania["avg_growth_pct"] is None

    # India (row 34): "- 0.01 - - - - -" — share "-" is a real zero, growth "-" is null.
    india = by_name["India"]
    assert india["no"] == 34
    assert india["values_usd"] == {"2020": 0.0, "2021": 10.0, "2022": 0.0, "2023": 0.0, "2024": 0.0}
    assert india["share_pct"] == 0.0
    assert india["avg_growth_pct"] is None

    # Kuwait (row 40): "- - - - - - -9.31" — every value/share is a real zero, but growth
    # is an ACTUAL negative number, not a dash — must not be nulled out like the others.
    kuwait = by_name["Kuwait"]
    assert kuwait["no"] == 40
    assert kuwait["values_usd"] == {"2020": 0.0, "2021": 0.0, "2022": 0.0, "2023": 0.0, "2024": 0.0}
    assert kuwait["share_pct"] == 0.0
    assert kuwait["avg_growth_pct"] == -9.31


def test_entity_page_rejects_row_label_mismatch():
    # A 24.* page's rows are labeled "Product" (goods sold to that country) — passing
    # "Market" (the 25.* shape) against it must fail loudly, not silently misparse.
    with pytest.raises(ValueError):
        _parse_entity_page(_pages(), ALBANIA_PAGE, "Market")


def test_parse_countries_finds_albania_and_china():
    toc = parse_toc((FIXTURES / EDB_2024).read_bytes())
    result = parse_countries((FIXTURES / EDB_2024).read_bytes(), toc=toc)
    assert result["ALBANIA"]["total"]["values_usd"]["2024"] == 9235.89
    assert result["CHINA"]["total"]["values_usd"]["2024"] == 251910.0


def test_parse_countries_blank_pages_do_not_crash_the_batch():
    # The fixture keeps ~98 of the ~100 TOC-listed 24.* pages blank (only Albania and
    # China are un-blanked) — one bad/blank page must never lose the other good ones.
    toc = parse_toc((FIXTURES / EDB_2024).read_bytes())
    result = parse_countries((FIXTURES / EDB_2024).read_bytes(), toc=toc)
    assert "ALBANIA" in result and "CHINA" in result
    assert "_errors" in result
    assert len(result["_errors"]) > 50  # the still-blank pages, contained rather than fatal
    assert "24.02" in result["_errors"]  # a specific known-blank page


def test_parse_products_finds_tea_and_green_tea():
    toc = parse_toc((FIXTURES / EDB_2024).read_bytes())
    result = parse_products((FIXTURES / EDB_2024).read_bytes(), toc=toc)
    tea = result["TEA (Tea Packets, Tea Bags, Tea in Bulk, Instant Tea & Green Tea etc.)"]
    assert tea["total"]["values_usd"]["2024"] == 1435860.0
    assert result["GREEN TEA"]["total"]["values_usd"]["2024"] == 5690.0


def test_parse_products_blank_pages_do_not_crash_the_batch():
    toc = parse_toc((FIXTURES / EDB_2024).read_bytes())
    result = parse_products((FIXTURES / EDB_2024).read_bytes(), toc=toc)
    assert "GREEN TEA" in result
    assert "_errors" in result  # the fixture's other 25.* pages in this TOC range are still blank


def test_parse_pdf_merges_countries_and_products_additively():
    result = parse_pdf((FIXTURES / EDB_2024).read_bytes())
    assert "_countries_error" not in result, result.get("_countries_error")
    assert "_products_error" not in result, result.get("_products_error")
    assert result["total_usd_mn"] == [15828, 12335, 14429, 14995, 15106, 16344]  # core contract still intact
    assert result["countries"]["ALBANIA"]["total"]["values_usd"]["2024"] == 9235.89
    assert result["products"]["GREEN TEA"]["total"]["values_usd"]["2024"] == 5690.0
