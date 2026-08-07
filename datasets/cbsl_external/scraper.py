"""CBSL external sector — reserve template, BOP quarterly, monthly trade."""

import sys

from pipeline.cbsl_tables import Source, harvest

from .parser import parse_bop, parse_reserves, parse_trade, total_series

DATASET = "cbsl_external"
LISTING = "https://www.cbsl.gov.lk/en/statistics/statistical-tables/external-sector"

SOURCES = [
    Source("reserves", LISTING, ("reserve data template", "latest")),
    Source("bop", LISTING, ("balance of payments", "bpm6", "quarterly")),
    Source("exports", LISTING, ("exports - monthly",)),
    Source("imports", LISTING, ("imports - monthly",)),
]


def _last(points: list[dict]) -> dict:
    return points[-1] if points else {}


def build(wb: dict) -> dict:
    reserves = parse_reserves(wb["reserves"])
    bop = parse_bop(wb["bop"])
    exports = parse_trade(wb["exports"], "exports")
    imports = parse_trade(wb["imports"], "imports")
    export_total, import_total = total_series(exports), total_series(imports)
    latest_month = _last(export_total).get("t")
    deficit = None
    if export_total and import_total and _last(import_total).get("t") == latest_month:
        deficit = _last(export_total)["v"] - _last(import_total)["v"]

    return {
        "reserves": reserves,
        "bop": bop,
        "exports": exports,
        "imports": imports,
        "latest": {
            "month": latest_month,
            "exports_usd_mn": _last(export_total).get("v"),
            "imports_usd_mn": _last(import_total).get("v"),
            "trade_balance_usd_mn": deficit,
            "reserves_as_of": reserves["as_of"],
            "official_reserve_assets_usd_mn": reserves["official_reserve_assets_usd_mn"],
            "gold_usd_mn": reserves["gold_usd_mn"],
            "bop_quarter": bop["quarters"][-1] if bop["quarters"] else None,
        },
    }


def run(_budget_seconds: float = 300) -> int:
    return harvest(DATASET, SOURCES, build, LISTING)


if __name__ == "__main__":
    run(float(sys.argv[1]) if len(sys.argv) > 1 else 300)
