import json
from pathlib import Path

from datasets.nmra_registrations.parser import clean_cell, summarize
from datasets.pucsl_generation.parser import build_clean
from datasets.sltda_arrivals.parser import parse_pdf as parse_sltda
from datasets.tbill_auctions.parser import parse_pdf as parse_tbill
from datasets.wer.parser import parse_pdf as parse_wer

FIXTURES = Path(__file__).parent / "fixtures"


def test_tbill_auction_release():
    result = parse_tbill((FIXTURES / "tbill_20260805.pdf").read_bytes())
    tenors = {r["tenor_days"]: r["way_pct"] for r in result["results"]}
    assert tenors.get(182) == 9.99
    assert tenors.get(364) == 10.19


def test_wer_district_table():
    result = parse_wer((FIXTURES / "wer_53_26.pdf").read_bytes())
    by_name = {d["district"]: d for d in result["districts"]}
    assert len(result["districts"]) >= 25
    assert by_name["Colombo"]["diseases"]["dengue"] == {"week": 1138, "cumulative": 9357}
    assert by_name["Colombo"]["district_id"] == "LK-11"
    assert "Nuwara Eliya" in by_name


def test_sltda_arrivals():
    result = parse_sltda((FIXTURES / "sltda_latest.pdf").read_bytes())
    assert result["months"], "no monthly rows parsed"
    assert result["ytd_total"] > 1_000_000
    countries = [m["country"] for m in result["top_markets_ytd"]]
    assert "India" in countries


def test_pucsl_build_clean():
    generation = json.loads((FIXTURES / "pucsl_generation.json").read_text())
    reservoir = json.loads((FIXTURES / "pucsl_reservoir.json").read_text())
    plants = json.loads((FIXTURES / "pucsl_plants.json").read_text()).get("data", [])
    complexes = json.loads((FIXTURES / "pucsl_complexes.json").read_text()).get("data", [])
    clean = build_clean("2026-08-04", generation, reservoir, plants, complexes)
    assert clean is not None
    assert clean["total_generation_mwh"] > 1000
    assert clean["reservoirs"] and clean["total_storage_gwh"] > 0
    # regression test for the complex->energyType join (audit: was 55.8% Unknown)
    assert clean["generation_by_fuel_mwh"].get("Unknown", 0) == 0
    assert abs(sum(clean["generation_by_fuel_mwh"].values()) - clean["total_generation_mwh"]) < 1
    assert clean["renewable_share_pct"] and 0 < clean["renewable_share_pct"] < 100
    # only one reportDate bucket may be aggregated
    assert clean["report_date"]
    # XSS-probe complex name must never survive sanitization
    assert all("<" not in f for f in clean["generation_by_fuel_mwh"])


def test_nmra_summarize_and_cleanup():
    # placeholders blank out; ordinary values are preserved verbatim (no rstrip truncation)
    assert clean_cell("***") == ""
    assert clean_cell("N/A") == ""
    assert clean_cell("  double  spaced  ") == "double spaced"
    assert clean_cell("BANGLADESH!") == "BANGLADESH!"
    header = ["GENERIC NAME", "BRAND", "COUNTRY"]
    rows = [["A", "B", "INDIA"], ["C", "D", "INDIA"], ["E", "F", "SRI LANKA"]]
    summary = summarize(header, rows)
    assert summary["total_registrations"] == 3
    assert summary["top_countries"][0] == {"country": "INDIA", "count": 2}


def test_edb_indicators_totals():
    from datasets.edb_indicators.parser import parse_text

    text = (FIXTURES / "edb_text.txt").read_text()
    result = parse_text(text)
    assert result["years"] == [2019, 2020, 2021, 2022, 2023, 2024]
    assert result["total_usd_mn"][-1] == 16344
    assert result["merchandise_usd_mn"][0] > 0
    assert len(result["services_usd_mn"]) == 6


def test_cbsl_weekly_prose():
    import re
    from datasets.cbsl_weekly.parser import parse_pdf  # noqa: F401  (parse_pdf needs PDF)
    from datasets.cbsl_weekly import parser as wp

    text = (FIXTURES / "wei_text.txt").read_text()
    # exercise the regex layer directly on the recorded prose
    out = {}
    m = re.search(rf"gross official reserves[^.]*?US dollars? {wp.MN}[^.]*?as at end (\w+ \d{{4}})", text, re.I)
    assert m and wp._num(m.group(1)) == 6458
    m2 = re.search(rf"Export earnings (increased|decreased) by ([\d.]+) per cent[^.]*?US dollars? {wp.MN}", text, re.I)
    assert m2 and wp._num(m2.group(3)) == 6903


def test_forbes_tea_table():
    from datasets.forbes_tea.parser import parse_pdf  # noqa: F401
    import re
    from datasets.forbes_tea import parser as tp

    text = (FIXTURES / "tea_qa.txt").read_text()
    rows = [l for l in text.split("\n") if tp.ROW_RE.match(l.strip())]
    assert len(rows) > 15
    m = tp.ROW_RE.match("01-JUL-2027 1,013 1,025 3,190 5,228 1071.14 957.22 1292.66 1183.94")
    assert m and m.group(3) == "2027"  # typo row matches; parser repairs the year


def test_treasury_phase1():
    from datasets.tbill_auctions.parser import parse_phase1

    result = parse_phase1((FIXTURES / "treasury_phase1.pdf").read_bytes())
    by_tenor = {r["tenor_days"]: r for r in result["results"]}
    assert by_tenor[91]["way_pct"] == 9.77 and by_tenor[91]["accepted_rs_mn"] == 72807
    assert by_tenor[364]["isin"] == "LKA36427H063"
    assert result["totals"]["accepted_rs_mn"] == 140000


def test_wer_table2():
    from datasets.wer.parser import parse_pdf

    clean = parse_pdf((FIXTURES / "wer_53_26.pdf").read_bytes())
    vpd = {r["disease"]: r for r in clean["vaccine_preventable"]}
    assert vpd["Measles"]["total_week"] == 5 and vpd["Measles"]["provinces"]["Sab"] == 5
    assert vpd["Mumps"]["total_week"] == 2 and vpd["Mumps"]["pct_difference"] == -10
    assert "Neonatal Tetanus" in vpd and "Japanese Encephalitis" in vpd
    assert clean["malaria_cases_month"] == 9
    assert clean["total"]["dengue"]["week"] == 5828
