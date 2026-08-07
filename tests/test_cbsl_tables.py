"""CBSL statistical-table parsing: shared cell helpers plus two fixtures that
pin the traps worth regression-testing — a mixed-type period header and a
mislabelled year block."""

from pathlib import Path

import pytest

from datasets.cbsl_activity.parser import parse_iip
from datasets.cbsl_prices.parser import parse_cpi
from pipeline import xlsx

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    return xlsx.load((FIXTURES / name).read_bytes())


class TestCells:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            (1234.5, 1234.5),
            ("1,234.5", 1234.5),
            ("(1.2)", -1.2),          # parenthesised negative
            ("6,458 (II)", 6458.0),   # roman-numeral footnote marker
            ("n.a", None),
            ("-", None),
            ("...", None),
            ("", None),
            (None, None),
        ],
    )
    def test_num(self, raw, expected):
        assert xlsx.num(raw) == expected

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Jan-26 (b)", "2026-01"),   # trade headers go text partway along
            ("Jun-26 (b)", "2026-06"),
            ("Dec-2019", "2019-12"),
            ("Category", None),
            ("", None),
        ],
    )
    def test_month_stamp(self, raw, expected):
        assert xlsx.month_stamp(raw) == expected

    def test_month_stamp_reads_real_dates(self):
        import datetime

        assert xlsx.month_stamp(datetime.datetime(2007, 1, 1)) == "2007-01"

    def test_period_of(self):
        assert xlsx.period_of("2025 June") == "2025-06"
        assert xlsx.period_of("June 2025") == "2025-06"
        assert xlsx.period_of("Note: see below") is None

    def test_series_rounds_and_trims(self):
        points = {"2026-01": 1.23456789, "2026-02": 2.0, "2025-12": None}
        assert xlsx.series(points) == [{"t": "2026-01", "v": 1.2346}, {"t": "2026-02", "v": 2.0}]
        assert xlsx.series(points, keep=1) == [{"t": "2026-02", "v": 2.0}]


class TestCpi:
    @pytest.fixture(scope="class")
    def ccpi(self):
        return parse_cpi(load("cbsl_ccpi_20260731.xlsx"), "CCPI")

    def test_splits_measures_and_core_variants(self, ccpi):
        assert set(ccpi) == {
            "index", "index_core",
            "monthly_pct", "monthly_pct_core",
            "yoy_pct", "yoy_pct_core",
            "annual_avg_pct", "annual_avg_pct_core",
        }

    def test_latest_matches_published_figures(self, ccpi):
        # Cross-checked against CBSL's inflation widget for the same month.
        assert ccpi["yoy_pct"][-1] == {"t": "2026-07", "v": 7.3}
        assert ccpi["yoy_pct_core"][-1] == {"t": "2026-07", "v": 4.4}
        assert ccpi["index"][-1] == {"t": "2026-07", "v": 208.2}

    def test_is_a_rolling_window_not_full_history(self, ccpi):
        # These workbooks carry ~14 months; long history comes from the widget.
        assert 10 <= len(ccpi["index"]) <= 24


class TestIip:
    @pytest.fixture(scope="class")
    def iip(self):
        return parse_iip(load("cbsl_iip_20260727.xlsx"))

    def test_reads_the_total_row_not_the_sheet_title(self, iip):
        # Row 1 repeats "Index of Industrial Production (2015=100)" as a title.
        assert iip["total"][0]["t"] == "2016-01"
        assert iip["total"][-1]["t"] == "2026-05"

    def test_derives_year_from_block_position_over_a_bad_label(self, iip):
        """CBSL labels its final two blocks '2025 (a)' and '2025 (b)'. The
        second is really 2026 — eleventh block after 2016, five months, values
        above the same months of 2025 rather than a revision of them."""
        assert any("2025" in note and "2026" in note for note in iip["notes"])
        assert iip["total"][-1] == {"t": "2026-05", "v": 99.9}
        assert [p["t"] for p in iip["total"]][-5:] == [
            "2026-01", "2026-02", "2026-03", "2026-04", "2026-05"
        ]

    def test_industries_carry_isic_codes(self, iip):
        assert len(iip["by_industry"]) == 20
        assert iip["by_industry"][0]["isic"] == "10"
