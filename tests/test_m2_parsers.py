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
    clean = build_clean("2026-08-04", generation, reservoir, plants)
    assert clean is not None
    assert clean["total_generation_mwh"] > 1000
    assert clean["reservoirs"] and clean["total_storage_gwh"] > 0
    assert clean["generation_by_fuel_mwh"]


def test_nmra_summarize_and_cleanup():
    assert clean_cell("BANGLADESH!") == "BANGLADESH"
    header = ["GENERIC NAME", "BRAND", "COUNTRY"]
    rows = [["A", "B", "INDIA"], ["C", "D", "INDIA"], ["E", "F", "SRI LANKA"]]
    summary = summarize(header, rows)
    assert summary["total_registrations"] == 3
    assert summary["top_countries"][0] == {"country": "INDIA", "count": 2}
