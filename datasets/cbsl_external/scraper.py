"""CBSL external sector — reserve template, BOP quarterly, monthly trade."""

import sys

from pipeline.cbsl_tables import Source, harvest

from .parser import (
    parse_bop,
    parse_hierarchy,
    parse_dated_grid,
    parse_month_year_matrix,
    parse_reserves,
    parse_trade,
    total_series,
)

DATASET = "cbsl_external"
LISTING = "https://www.cbsl.gov.lk/en/statistics/statistical-tables/external-sector"

SOURCES = [
    Source("reserves", LISTING, ("reserve data template", "latest")),
    Source("bop", LISTING, ("balance of payments", "bpm6", "quarterly")),
    Source("exports", LISTING, ("exports - monthly",)),
    Source("imports", LISTING, ("imports - monthly",)),
    Source("tourism", LISTING, ("earnings from tourism",)),
    Source("remittances", LISTING, ("workers remittances",)),
    Source("services", LISTING, ("monthly services sector",)),
    Source("current_account", LISTING, ("monthly current account",)),
    Source("cse_inflows", LISTING, ("inflows to the colombo stock exchange",)),
    Source("gsec_inflows", LISTING, ("treasury bills and treasury bonds inflows",)),
]


def _last(points: list[dict]) -> dict:
    return points[-1] if points else {}


def _to_vintage(points: list[dict], vintage: str) -> list[dict]:
    """Drop months that postdate the workbook's own publication.

    The T-bill/bond inflow matrix pads the rest of the current year with exact
    zeros, which would otherwise publish "Rs 0 inflows" for months that have
    not happened yet.
    """
    cutoff = f"{vintage[:4]}-{vintage[4:6]}"
    kept = [p for p in points if p["t"] <= cutoff]
    # The current year is also padded with exact zeros up to the vintage month.
    # A genuine zero-inflow month is indistinguishable from that padding, so a
    # trailing run of zeros is dropped rather than published as real.
    while kept and kept[-1]["v"] == 0:
        kept.pop()
    return kept


def build(wb: dict, vintage: str = "99991231") -> dict:
    reserves = parse_reserves(wb["reserves"])
    bop = parse_bop(wb["bop"])
    exports = parse_trade(wb["exports"], "exports")
    imports = parse_trade(wb["imports"], "imports")
    tourism = _to_vintage(parse_month_year_matrix(wb["tourism"]), vintage)
    remittances = _to_vintage(parse_month_year_matrix(wb["remittances"]), vintage)
    services = parse_hierarchy(wb["services"], "inflows")
    # Foreign portfolio flows: the fastest-moving part of the external account.
    cse_inflows = {k: _to_vintage(v, vintage) for k, v in parse_dated_grid(wb["cse_inflows"]).items()}
    gsec_inflows = _to_vintage(parse_month_year_matrix(wb["gsec_inflows"]), vintage)
    current_account = parse_hierarchy(wb["current_account"], "ca")
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
        "tourism_usd_mn": tourism,
        "remittances_usd_mn": remittances,
        "services_inflows": services,
        "cse_inflows": cse_inflows,
        "gsec_inflows_usd_mn": gsec_inflows,
        "current_account": current_account,
        "latest": {
            "month": latest_month,
            "exports_usd_mn": _last(export_total).get("v"),
            "imports_usd_mn": _last(import_total).get("v"),
            "trade_balance_usd_mn": deficit,
            "reserves_as_of": reserves["as_of"],
            "official_reserve_assets_usd_mn": reserves["official_reserve_assets_usd_mn"],
            "gold_usd_mn": reserves["gold_usd_mn"],
            "bop_quarter": bop["quarters"][-1] if bop["quarters"] else None,
            "tourism_month": _last(tourism).get("t"),
            "tourism_usd_mn": _last(tourism).get("v"),
            "remittances_month": _last(remittances).get("t"),
            "remittances_usd_mn": _last(remittances).get("v"),
            "services_inflows_usd_mn": (services[0]["points"][-1]["v"] if services else None),
            "cse_secondary_inflows_usd_mn": _last(cse_inflows.get("secondarymarket_inflows", [])).get("v"),
            "cse_secondary_outflows_usd_mn": _last(cse_inflows.get("secondarymarket_outflows", [])).get("v"),
            "gsec_inflows_usd_mn": _last(gsec_inflows).get("v"),
            "portfolio_month": _last(gsec_inflows).get("t"),
        },
    }


def run(_budget_seconds: float = 300) -> int:
    return harvest(DATASET, SOURCES, build, LISTING)


if __name__ == "__main__":
    run(float(sys.argv[1]) if len(sys.argv) > 1 else 300)
