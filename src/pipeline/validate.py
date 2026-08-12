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


# Datasets whose originals must be text-layer PDFs; a scanned/image-only
# edition means the publisher changed format and the parser here is blind.
EXPECTED_TEXT_PDF = {
    "cbsl_daily",
    "cbsl_price_report",
    "cbsl_weekly",
    "wer",
    "edb_indicators",
    "tbill_auctions",
    "sltda_arrivals",
    "forbes_tea",
}
TRIAGE_CONFIDENCE = 0.7


def _triage(clean: dict) -> list[str]:
    """Gate on the _meta.inspection record stamped by store.write_doc. Only a
    confident scanned/image_based verdict fires; "mixed" and encoding flags are
    recorded but never gate (kerning/z-order quirks must not quarantine)."""
    insp = (clean.get("_meta") or {}).get("inspection") or {}
    pdf_type = insp.get("pdf_type")
    if pdf_type in ("scanned", "image_based") and insp.get("confidence", 0) >= TRIAGE_CONFIDENCE:
        return [f"pdf classified {pdf_type} (confidence {insp['confidence']}); expected text-based"]
    return []


def validate(dataset: str, clean: dict) -> list[str]:
    checker = _CHECKERS.get(dataset)
    errors = checker(clean) if checker else []
    if dataset in EXPECTED_TEXT_PDF:
        errors += _triage(clean)
    return errors


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
    fx = clean.get("fx_tt", {})
    for cur, pair in fx.items():
        if pair["tt_sell"] <= pair["tt_buy"]:
            errors.append(f"{cur}: TT sell <= buy")
    usd = fx.get("usd", {}).get("tt_sell")
    if usd is not None and not 250 <= usd <= 450:
        errors.append(f"USD TT {usd} outside [250,450]")
    mix = clean.get("electricity", {}).get("generation_mix_pct")
    if mix and abs(sum(mix.values()) - 100) > 0.6:
        errors.append(f"generation mix sums to {sum(mix.values())}")
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
        other = sum(r["arrivals"] for r in top10)
        if other > headline:
            errors.append("top-10 arrivals exceed monthly headline")
    daily = clean.get("daily", [])
    if daily:
        if any(d["arrivals"] <= 0 or d["arrivals"] > 25000 for d in daily):
            errors.append("daily arrival outside plausible band")
        if clean.get("daily_complete") and abs(clean.get("daily_sum", 0) - (headline or 0)) > 2:
            errors.append("daily_complete but sum != headline")
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


@register("forbes_tea")
def _forbes_tea(clean: dict) -> list[str]:
    errors = []
    for s in clean.get("sales", []):
        if not s["sale_date"].startswith(str(clean.get("year"))):
            errors.append(f"sale {s['sale_date']} outside year")
        if not 300 <= s["avg_rs"]["total"] <= 3000:
            errors.append(f"avg {s['avg_rs']['total']} outside [300,3000]")
    if clean.get("repaired_year_rows", 0) > 3:
        errors.append("too many repaired year rows — layout suspect")
    return errors


# --- CBSL statistical-table families -------------------------------------
# These parse many columns at once, so the checks target the handful of
# figures a silent layout shift would corrupt first.


def _latest(clean: dict) -> dict:
    return clean.get("latest") or {}


@register("cbsl_prices")
def _cbsl_prices(clean: dict) -> list[str]:
    errors = []
    latest = _latest(clean)
    index = latest.get("ccpi_index")
    if index is not None and not 100 <= index <= 500:
        errors.append(f"CCPI index {index} outside [100, 500] for a 2021=100 base")
    for name in ("ccpi_yoy_pct", "ncpi_yoy_pct"):
        value = latest.get(name)
        if value is not None and not -30 <= value <= 100:
            errors.append(f"{name}={value} outside [-30, 100]")
    if not clean.get("ccpi", {}).get("index"):
        errors.append("no CCPI index series")
    return errors


@register("cbsl_activity")
def _cbsl_activity(clean: dict) -> list[str]:
    errors = []
    latest = _latest(clean)
    for name in ("pmi_manufacturing", "pmi_services", "pmi_construction"):
        value = latest.get(name)
        if value is not None and not 0 <= value <= 100:
            errors.append(f"{name}={value} is not a diffusion index")
    iip = latest.get("iip")
    if iip is not None and not 20 <= iip <= 400:
        errors.append(f"IIP {iip} outside [20, 400]")
    if not clean.get("iip", {}).get("total"):
        errors.append("no IIP total series")
    return errors


@register("cbsl_monetary")
def _cbsl_monetary(clean: dict) -> list[str]:
    errors = []
    latest = _latest(clean)
    for name in ("opr_pct", "sdfr_pct", "slfr_pct", "bank_rate_pct"):
        value = latest.get(name)
        if value is not None and not 0 < value < 50:
            errors.append(f"{name}={value} implausible")
    sdfr, slfr = latest.get("sdfr_pct"), latest.get("slfr_pct")
    if sdfr is not None and slfr is not None and slfr < sdfr:
        errors.append(f"SLFR {slfr} below SDFR {sdfr} — corridor inverted")
    reserve = latest.get("reserve_money_rs_mn")
    if reserve is not None and reserve <= 0:
        errors.append(f"reserve money {reserve} not positive")
    return errors


@register("cbsl_fiscal")
def _cbsl_fiscal(clean: dict) -> list[str]:
    errors = []
    latest = _latest(clean)
    debt_pct = latest.get("debt_pct_gdp")
    if debt_pct is not None and not 10 <= debt_pct <= 300:
        errors.append(f"debt {debt_pct}% of GDP outside [10, 300]")
    # Total financing closes the overall deficit by construction; a mismatch
    # means the two columns have drifted apart in the header map.
    deficit = latest.get("overall_deficit_rs_mn")
    financing = (clean.get("operations", {}).get("financing_totalfinancing") or [{}])[-1].get("v")
    if deficit is not None and financing is not None and abs(financing + deficit) > max(1.0, abs(deficit) * 0.01):
        errors.append(f"financing {financing} does not offset deficit {deficit}")
    return errors


@register("cbsl_external")
def _cbsl_external(clean: dict) -> list[str]:
    errors = []
    latest = _latest(clean)
    reserves = latest.get("official_reserve_assets_usd_mn")
    if reserves is not None and not 0 < reserves < 100_000:
        errors.append(f"official reserve assets {reserves} USD mn implausible")
    exports, imports = latest.get("exports_usd_mn"), latest.get("imports_usd_mn")
    for name, value in (("exports", exports), ("imports", imports)):
        if value is not None and not 0 < value < 20_000:
            errors.append(f"monthly {name} {value} USD mn implausible")
    balance = latest.get("trade_balance_usd_mn")
    if None not in (exports, imports, balance) and abs((exports - imports) - balance) > 1:
        errors.append("trade balance does not equal exports - imports")
    return errors


@register("cbsl_financial")
def _cbsl_financial(clean: dict) -> list[str]:
    errors = []
    latest = clean.get("latest") or {}
    capital = latest.get("total_capital_ratio_pct")
    tier1 = latest.get("tier1_capital_ratio_pct")
    if capital is not None and not 0 < capital < 100:
        errors.append(f"total capital ratio {capital} implausible")
    if capital is not None and tier1 is not None and tier1 > capital:
        errors.append(f"tier 1 ratio {tier1} exceeds total capital ratio {capital}")
    npl = latest.get("npl_ratio_pct")
    if npl is not None and not 0 <= npl < 100:
        errors.append(f"stage 3 ratio {npl} implausible")
    if not clean.get("soundness"):
        errors.append("no soundness sheets parsed")
    return errors


@register("cbsl_price_report")
def _cbsl_price_report(clean: dict) -> list[str]:
    """The report states its movers twice — as page-1 highlights and inside the
    page-2 retail columns — so the two must agree. That cross-check is what
    proves the split-digit reassembly ("1" + "28.00" -> 128.00) landed
    correctly, since a misjoin would show up as an order-of-magnitude gap."""
    errors = []
    items = clean.get("items") or []
    if len(items) < 10:
        errors.append(f"only {len(items)} commodity rows parsed")

    for item in items:
        for column, pair in (item.get("prices") or {}).items():
            for when, value in pair.items():
                if value is not None and not 0 < value < 100_000:
                    errors.append(f"{item['item']} {column} {when}={value} implausible")

    by_item = {i["item"].lower(): i for i in items}
    for highlight in clean.get("highlights") or []:
        row = by_item.get(highlight["item"].lower())
        if row is None:
            continue  # fish and some staples are highlighted but not tabulated
        for move in highlight["moves"]:
            key = f"retail_{move['market'].lower()}"
            tabulated = (row.get("prices") or {}).get(key)
            if not tabulated:
                continue
            for when in ("previous", "today"):
                stated, listed = move.get(when), tabulated.get(when)
                if None not in (stated, listed) and abs(stated - listed) > 0.01:
                    errors.append(
                        f"{highlight['item']} {move['market']} {when}: "
                        f"highlight {stated} != table {listed}"
                    )
    return errors
