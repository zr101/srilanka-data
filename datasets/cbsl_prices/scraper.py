"""CBSL prices — CCPI/NCPI index levels and wage rate indices."""

import sys

from pipeline.cbsl_tables import Source, harvest

from .parser import latest_of, parse_cpi, parse_wages

DATASET = "cbsl_prices"
LISTING = "https://www.cbsl.gov.lk/en/statistics/statistical-tables/real-sector/prices-wages-employment"

SOURCES = [
    Source("ccpi", LISTING, ("ccpi",)),
    Source("ncpi", LISTING, ("ncpi",)),
    Source("wages", LISTING, ("wage",)),
]


def build(wb: dict) -> dict:
    ccpi = parse_cpi(wb["ccpi"], "CCPI")
    ncpi = parse_cpi(wb["ncpi"], "NCPI")
    wages = parse_wages(wb["wages"])
    return {
        # Rolling ~14-month window: these workbooks carry recent months only.
        # Long Y-o-Y history comes from CBSL's inflation widget instead
        # (srilankamonitor lib/sources/cbslInflation.ts).
        "ccpi": ccpi,
        "ncpi": ncpi,
        "wages": wages,
        "latest": {
            "ccpi_month": (latest_of(ccpi.get("index", [])) or {}).get("t"),
            "ccpi_index": (latest_of(ccpi.get("index", [])) or {}).get("v"),
            "ccpi_yoy_pct": (latest_of(ccpi.get("yoy_pct", [])) or {}).get("v"),
            "ccpi_monthly_pct": (latest_of(ccpi.get("monthly_pct", [])) or {}).get("v"),
            "ccpi_annual_avg_pct": (latest_of(ccpi.get("annual_avg_pct", [])) or {}).get("v"),
            "ncpi_month": (latest_of(ncpi.get("index", [])) or {}).get("t"),
            "ncpi_index": (latest_of(ncpi.get("index", [])) or {}).get("v"),
            "ncpi_yoy_pct": (latest_of(ncpi.get("yoy_pct", [])) or {}).get("v"),
            "wage_public_real": (latest_of(wages.get("public_real", [])) or {}).get("v"),
            "wage_informal_real": (latest_of(wages.get("informal_private_real", [])) or {}).get("v"),
            "wage_month": (latest_of(wages.get("public_real", [])) or {}).get("t"),
        },
    }


def run(_budget_seconds: float = 300) -> int:
    return harvest(DATASET, SOURCES, build, LISTING)


if __name__ == "__main__":
    run(float(sys.argv[1]) if len(sys.argv) > 1 else 300)
