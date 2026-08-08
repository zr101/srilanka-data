"""CBSL fiscal sector — government fiscal operations and outstanding debt."""

import sys

from pipeline.cbsl_tables import Source, harvest

from .parser import parse_debt, parse_expenditure, parse_operations, parse_revenue

DATASET = "cbsl_fiscal"
LISTING = "https://www.cbsl.gov.lk/en/statistics/statistical-tables/fiscal-sector"

SOURCES = [
    Source("operations", LISTING, ("fiscal operations",)),
    Source("debt", LISTING, ("outstanding government debt",)),
    Source("revenue", LISTING, ("classification of government revenue",)),
    Source("expenditure", LISTING, ("classification of government expenditure",)),
]


def _last(points: list[dict]) -> dict:
    return points[-1] if points else {}


def build(wb: dict) -> dict:
    ops = parse_operations(wb["operations"])
    debt = parse_debt(wb["debt"])
    revenue = parse_revenue(wb["revenue"])
    expenditure = parse_expenditure(wb["expenditure"])
    return {
        "operations": ops,
        "debt": debt,
        "revenue": revenue,
        "expenditure": expenditure,
        "latest": {
            "year": _last(ops.get("revenueandgrants", [])).get("t"),
            "revenue_and_grants_rs_mn": _last(ops.get("revenueandgrants", [])).get("v"),
            "expenditure_rs_mn": _last(ops.get("expenditure_total", [])).get("v"),
            "overall_deficit_rs_mn": _last(ops.get("overallbudgetsurplusdeficit", [])).get("v"),
            "primary_balance_rs_mn": _last(ops.get("primaryacsurplusdeficit", [])).get("v"),
            "total_debt_rs_mn": _last(debt.get("totaldebt", [])).get("v"),
            "debt_pct_gdp": _last(debt.get("asaofgdpg_total", [])).get("v"),
            "domestic_debt_pct_gdp": _last(debt.get("asaofgdpg_domestic", [])).get("v"),
            "foreign_debt_pct_gdp": _last(debt.get("asaofgdpg_foreign", [])).get("v"),
        },
    }


def run(_budget_seconds: float = 300) -> int:
    return harvest(DATASET, SOURCES, build, LISTING)


if __name__ == "__main__":
    run(float(sys.argv[1]) if len(sys.argv) > 1 else 300)
