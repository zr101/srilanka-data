"""Daily Price Report: the split-digit reassembly and the two edition variants."""

from pathlib import Path

import pytest

from datasets.cbsl_price_report.parser import parse_pdf

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def tuesday():
    return parse_pdf((FIXTURES / "price_report_20260807.pdf").read_bytes())


@pytest.fixture(scope="module")
def monday():
    return parse_pdf((FIXTURES / "price_report_20260803.pdf").read_bytes())


def test_reads_the_report_date(tuesday):
    assert tuesday["report_date_text"] == "07 August 2026"


def test_rejoins_split_digits(tuesday):
    """pdfplumber emits "300.00" as the words '3' and '00.00'; splitting on
    whitespace would read Rs 300 as Rs 3."""
    beans = next(i for i in tuesday["items"] if i["item"] == "Beans")
    assert beans["prices"]["wholesale_pettah"] == {"previous": 300.0, "today": 300.0}
    assert beans["prices"]["retail_narahenpita"] == {"previous": 560.0, "today": 560.0}
    assert all(v is None or v >= 10 for i in tuesday["items"] for p in i["prices"].values() for v in p.values())


def test_covers_every_market_column(tuesday):
    assert tuesday["markets"] == ["Pettah", "Dambulla"]
    assert len(tuesday["items"]) == 42
    carrot = next(i for i in tuesday["items"] if i["item"] == "Carrot")
    assert set(carrot["prices"]) == {
        "wholesale_pettah", "wholesale_dambulla",
        "retail_pettah", "retail_dambulla", "retail_narahenpita",
    }


def test_highlights_agree_with_the_table(tuesday):
    """The report states its movers twice; retail columns must match."""
    carrot_row = next(i for i in tuesday["items"] if i["item"] == "Carrot")
    carrot_hl = next(h for h in tuesday["highlights"] if h["item"] == "Carrot")
    pettah = next(m for m in carrot_hl["moves"] if m["market"] == "Pettah")
    assert pettah["previous"] == carrot_row["prices"]["retail_pettah"]["previous"]
    assert pettah["today"] == carrot_row["prices"]["retail_pettah"]["today"]
    assert carrot_hl["direction"] == "declined"


def test_reads_wrapped_fish_headings(tuesday):
    """Fish blocks split the commodity name and its verb across two lines."""
    assert {"Balaya", "Salaya"} <= {h["item"] for h in tuesday["highlights"]}


def test_monday_compares_to_last_friday(monday):
    """Monday editions swap 'Yesterday' for 'Last Friday' and split the header
    across two lines; columns come from the data so the parse is unaffected."""
    assert monday["compares_to"] == "last Friday"
    assert len(monday["items"]) == 42


def test_orphaned_rows_are_dropped_and_reported(monday):
    """This edition interleaves two columns into one line, destroying a
    heading. Its price rows must be dropped, not misattributed."""
    assert monday["notes"] and "dropped" in monday["notes"][0]
    linna = next((h for h in monday["highlights"] if h["item"] == "Linna"), None)
    assert linna is not None
    assert all(m["market"] not in ("Pettah", "Dambulla") for m in linna["moves"])
