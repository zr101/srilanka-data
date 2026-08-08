"""CBSL activity — Index of Industrial Production, PMI and Business Sentiment."""

import sys

from pipeline.cbsl_tables import Source, harvest

from .parser import parse_bsi, parse_housing, parse_iip, parse_pmi

DATASET = "cbsl_activity"
PRODUCTION = "https://www.cbsl.gov.lk/en/statistics/statistical-tables/real-sector/production-indicators"
PMI_PAGE = "https://www.cbsl.gov.lk/en/statistics/business-surveys/sl-purchasing-managers-index-survey"
BSI_PAGE = "https://www.cbsl.gov.lk/en/statistics/business-surveys/business-outlook-survey"

SOURCES = [
    Source("iip", PRODUCTION, ("industrial production",)),
    Source("pmi", PMI_PAGE, ("pmi",)),
    Source("bsi", BSI_PAGE, ("bsi",), required=False),
    Source("housing", PRODUCTION, ("housing approval index – quarterly",), required=False),
]


def _last(points: list[dict]) -> dict:
    return points[-1] if points else {}


def build(wb: dict) -> dict:
    iip = parse_iip(wb["iip"])
    pmi = parse_pmi(wb["pmi"])
    bsi = parse_bsi(wb["bsi"]) if "bsi" in wb else {}
    housing = parse_housing(wb["housing"]) if "housing" in wb else {}

    def headline(sector: str) -> list[dict]:
        """The sector's own PMI row is the first series on its sheet."""
        return next(iter(pmi.get(sector, {}).values()), [])

    return {
        "iip": iip,
        "pmi": pmi,
        "bsi": bsi,
        "housing_approvals": housing,
        "latest": {
            "iip_month": _last(iip["total"]).get("t"),
            "iip": _last(iip["total"]).get("v"),
            "pmi_manufacturing": _last(headline("manufacturing")).get("v"),
            "pmi_services": _last(headline("services")).get("v"),
            "pmi_construction": _last(headline("construction")).get("v"),
            "pmi_month": _last(headline("manufacturing")).get("t"),
            "bsi_business_conditions": _last(bsi.get("businessconditionlevel", [])).get("v"),
            "bsi_quarter": _last(bsi.get("businessconditionlevel", [])).get("t"),
        },
    }


def run(_budget_seconds: float = 300) -> int:
    return harvest(DATASET, SOURCES, build, PRODUCTION)


if __name__ == "__main__":
    run(float(sys.argv[1]) if len(sys.argv) > 1 else 300)
