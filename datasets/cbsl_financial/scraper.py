"""CBSL financial sector — banking soundness indicators."""

import sys

from pipeline.cbsl_tables import Source, harvest

from .parser import find_indicator, parse_finance_companies, parse_outlets, parse_soundness

DATASET = "cbsl_financial"
LISTING = "https://www.cbsl.gov.lk/en/statistics/statistical-tables/financial-sector"

SOURCES = [
    Source("soundness", LISTING, ("soundness indicators", "q1 2022")),
    Source("balance_sheet", LISTING, ("assets, liabilities, and capital", "q1 2022")),
    Source("earnings", LISTING, ("earnings and profits", "q1 2022")),
    Source("outlets", LISTING, ("distribution of banking outlets",)),
    Source("finance_companies", LISTING, ("finance companies sector",), required=False),
]


def _last(points: list[dict]) -> dict:
    return points[-1] if points else {}


def build(wb: dict) -> dict:
    soundness = parse_soundness(wb["soundness"])
    # Most of the financial-sector family shares the year-over-quarter layout,
    # but not all of it — "Distribution of Banking Outlets" is annual. A
    # workbook that does not match is skipped and named rather than failing the
    # whole dataset, since the soundness indicators are the load-bearing part.
    extra: dict[str, dict] = {}
    skipped: list[str] = []
    parsers = {"finance_companies": parse_finance_companies, "outlets": parse_outlets}
    for name in ("balance_sheet", "earnings", "outlets", "finance_companies"):
        if name not in wb:
            continue
        try:
            extra[name] = parsers.get(name, parse_soundness)(wb[name])
        except ValueError as err:
            skipped.append(f"{name}: {err}")
            print(f"  {name}: skipped ({err})")
    capital = find_indicator(soundness, "capitaladequacyratios", "total capital ratio")
    tier1 = find_indicator(soundness, "capitaladequacyratios", "tier 1 capital ratio")
    # CBSL renamed non-performing loans to IFRS 9 "Stage 3 Loans"; the headline
    # ratio is the excluding-undrawn one. Both wordings are tried so a revert
    # upstream doesn't blank the field.
    npl = find_indicator(soundness, "assetsquality", "stage 3 loans", "excluding") or find_indicator(
        soundness, "assetsquality", "non performing"
    )
    liquidity = find_indicator(soundness, "liquidity", "rupee liquidity coverage")
    hqla = find_indicator(soundness, "liquidity", "high quality liquid assets")
    return {
        "soundness": soundness,
        **extra,
        "skipped": skipped,
        "latest": {
            "quarter": _last(capital).get("t"),
            "total_capital_ratio_pct": _last(capital).get("v"),
            "tier1_capital_ratio_pct": _last(tier1).get("v"),
            "npl_ratio_pct": _last(npl).get("v"),
            "rupee_lcr_pct": _last(liquidity).get("v"),
            "hqla_to_assets_pct": _last(hqla).get("v"),
            "roe_pct": _last(find_indicator(soundness, "earningsprofits", "return on equity")).get("v"),
        },
    }


def run(_budget_seconds: float = 300) -> int:
    return harvest(DATASET, SOURCES, build, LISTING)


if __name__ == "__main__":
    run(float(sys.argv[1]) if len(sys.argv) > 1 else 300)
