"""Declarative post-parse validation. A dataset registers a checker returning a
list of error strings; any error quarantines the doc instead of publishing it."""

from collections.abc import Callable

Checker = Callable[[dict], list[str]]
_CHECKERS: dict[str, Checker] = {}


def register(dataset: str):
    def wrap(fn: Checker) -> Checker:
        _CHECKERS[dataset] = fn
        return fn

    return wrap


def validate(dataset: str, clean: dict) -> list[str]:
    checker = _CHECKERS.get(dataset)
    return checker(clean) if checker else []


# --- built-in checkers (extend per dataset as parsers deepen) ---


@register("pucsl_generation")
def _pucsl(clean: dict) -> list[str]:
    errors = []
    fuels = clean.get("generation_by_fuel_mwh", {})
    total = clean.get("total_generation_mwh") or 0
    unknown = fuels.get("Unknown", 0)
    if total and unknown / total > 0.01:
        errors.append(f"Unknown fuel share {unknown / total:.1%} > 1%")
    if abs(sum(fuels.values()) - total) > 1:
        errors.append("sum(by_fuel) != total")
    if not 25_000 <= total <= 75_000:
        errors.append(f"daily total {total} outside [25k, 75k] MWh")
    if any("<" in f or ">" in f for f in fuels):
        errors.append("markup in fuel name")
    return errors


@register("cbsl_daily")
def _cbsl_daily(clean: dict) -> list[str]:
    errors = []
    tbill = clean.get("tbill", {})
    for tenor, v in tbill.items():
        if v is not None and not 0 < v < 50:
            errors.append(f"tbill {tenor}={v} implausible")
    opr = clean.get("opr")
    if opr is not None and not 3 <= opr <= 20:
        errors.append(f"OPR {opr} outside [3,20]")
    awpr = clean.get("awpr")
    if awpr is not None and opr is not None and not opr - 1 <= awpr <= opr + 10:
        errors.append(f"AWPR {awpr} vs OPR {opr} out of band")
    return errors


@register("sltda_arrivals")
def _sltda(clean: dict) -> list[str]:
    errors = []
    months = clean.get("months", [])
    ytd = clean.get("ytd_total")
    if months and ytd is not None:
        if sum(m["arrivals_this_year"] for m in months) != ytd:
            errors.append("sum(months) != ytd_total")
    top10 = clean.get("top_markets_month", [])
    headline = clean.get("month_headline")
    if top10 and headline:
        share_sum = sum(r.get("share_pct", 0) for r in top10)
        if share_sum and not 40 <= share_sum <= 101:
            errors.append(f"top-10 share sum {share_sum} implausible")
    return errors


@register("cbsl_weekly")
def _cbsl_weekly(clean: dict) -> list[str]:
    errors = []
    exp, imp, deficit = (
        clean.get("exports_usd_mn"),
        clean.get("imports_usd_mn"),
        clean.get("trade_deficit_usd_mn"),
    )
    if None not in (exp, imp, deficit) and abs((imp - exp) - deficit) > 2:
        errors.append("trade deficit != imports - exports")
    res = clean.get("reserves_usd_mn")
    if res is not None and not 1_000 <= res <= 20_000:
        errors.append(f"reserves {res} outside [1k, 20k] USD mn")
    return errors
