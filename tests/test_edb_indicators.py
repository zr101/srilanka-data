from pathlib import Path

from datasets.edb_indicators.parser import (
    find_table_text,
    parse_pdf,
    parse_table13,
    parse_table17,
    parse_text,
    parse_toc,
)

FIXTURES = Path(__file__).parent / "fixtures"

# edb_2024.pdf / edb_2023.pdf are trimmed from the real ~340-page, ~3-22MB EDB ebooks
# down to ~70 pages, ~200-600KB. Trimming is BLANK-IN-PLACE, not truncation: every
# page from index 0 up to the last one we need (70) is kept in the writer, with only
# the pages our parsers don't touch (front matter, graphs, tables outside 1/13/17/
# the TOC-map generalization check) replaced by a same-size blank page rather than
# removed. This preserves the pypdf page index of every kept page exactly as it is
# in the original document — which matters because parse_toc() derives its
# TOC-number -> pypdf-index offset from an anchor page's ACTUAL position (see its
# docstring). Naively dropping/reordering pages would shift that position and
# silently produce a wrong offset that still "works" (resolves to SOME page) but
# points at the wrong content. See datasets/edb_indicators/parser.py's TOC section
# comment for the offset derivation itself. If you add a 3rd/4th edition fixture,
# rebuild it the same way (pypdf.PdfWriter, add_blank_page for anything before your
# last needed page index, add_page for the rest) rather than slicing pages out.
EDB_2024 = "edb_2024.pdf"  # 6 year columns (2019-2024) — the previously-working case
EDB_2023 = "edb_2023.pdf"  # 5 year columns (2019-2023) — the edition that used to be silently skipped


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
    assert "_table17_error" not in result, result.get("_table17_error")
    assert result["table13"]["total"]["values"]["2024"] == 12771.63
    assert result["table17"]["grand_total"] == 18289
