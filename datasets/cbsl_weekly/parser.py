"""CBSL Weekly Economic Indicators: the tables are z-scrambled but the
first-page prose highlights carry the headline numbers in stable phrasing."""

import io
import re
from datetime import datetime

import pdfplumber
from pypdf import PdfReader

MN = r"([\d,]+)\s?m\s?n"  # numbers like "6,458 m n" (extraction splits 'mn')


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def parse_pdf(payload: bytes) -> dict:
    text = " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(payload)).pages[:3])
    text = re.sub(r"\s+", " ", text)

    out: dict = {}
    m = re.search(rf"gross official reserves[^.]*?US dollars? {MN}[^.]*?as at end (\w+ \d{{4}})", text, re.I)
    if m:
        out["reserves_usd_mn"] = _num(m.group(1))
        out["reserves_as_of"] = m.group(2)
    m = re.search(r"Year to date (depreciation|appreciation)[^.]*?([\d.]+) per cent as of (\d{1,2} \w+ \d{4})", text, re.I)
    if m:
        pct = float(m.group(2))
        out["rupee_ytd_pct"] = -pct if m.group(1).lower() == "depreciation" else pct
        out["rupee_as_of"] = m.group(3)
    m = re.search(rf"trade deficit \w+ to US dollars? {MN}", text, re.I)
    if m:
        out["trade_deficit_usd_mn"] = _num(m.group(1))
    m = re.search(rf"Export earnings (increased|decreased) by ([\d.]+) per cent[^.]*?US dollars? {MN}", text, re.I)
    if m:
        sign = 1 if m.group(1).lower() == "increased" else -1
        out["exports_usd_mn"] = _num(m.group(3))
        out["exports_yoy_pct"] = sign * float(m.group(2))
    m = re.search(rf"Import expenditure (increased|decreased) by ([\d.]+) per cent[^.]*?US dollars? {MN}", text, re.I)
    if m:
        sign = 1 if m.group(1).lower() == "increased" else -1
        out["imports_usd_mn"] = _num(m.group(3))
        out["imports_yoy_pct"] = sign * float(m.group(2))

    try:
        out["tables"] = parse_tables(payload)
    except Exception as err:  # tables are additive; prose highlights are the core contract
        out["_tables_error"] = str(err)

    # Mid-month editions genuinely lack the reserves/exports prose paragraphs (only
    # rupee-YTD prose is present then) — that's the documented root cause of prose
    # "failures", not a parse bug. So only raise if BOTH prose and tables came up
    # empty; if tables carried the data instead, that's the intended fallback.
    if "reserves_usd_mn" not in out and "exports_usd_mn" not in out and "tables" not in out:
        raise ValueError("WEI prose highlights not found — layout may have changed")
    return out


# --- Table extraction (reserves / external trade / trade indices / commodity prices) ---
#
# Section numbers float between editions (e.g. "4.3 External Trade" one week,
# "4.5 External Trade" the next, because an extra reserves table appears mid-month
# — see the two reserves captions below). Every table here is located by searching
# for its caption TEXT across the whole document, never by its leading "N.N" number.

_CID_LIGATURES = {"(cid:415)": "ti", "(cid:414)": "tf"}


def _clean_ligatures(text: str) -> str:
    for artifact, replacement in _CID_LIGATURES.items():
        text = text.replace(artifact, replacement)
    return text


NUM_TOKEN = re.compile(r"\(?-?[\d,]+\.\d+\)?")


def _signed_num(token: str) -> float:
    token = token.strip()
    negative = token.startswith("(") and token.endswith(")")
    value = float(token.strip("()").replace(",", ""))
    return -value if negative else value


# --- 4.x International Reserves (1 or 2 blocks per edition, see module docstring) ---

RESERVES_QUICK_RE = re.compile(r"Official Reserve Assets as at end (\w+ \d{4})")
RESERVES_DETAILED_RE = re.compile(
    r"International Reserves\s*&\s*Foreign Currency Liquidity as at end (\w+ \d{4})"
)

# (field key, line-anchored pattern). Anchoring each field to the *start* of its own
# line (not just "contains") keeps this from matching the caption line itself, or
# unrelated rows like "Other Reserve Assets" when looking for "Official Reserve Assets".
RESERVE_FIELDS = [
    ("official_reserve_assets_usd_mn", re.compile(r"^Official Reserve Assets\S*\s+([\d,]+)\s*$", re.M)),
    ("foreign_currency_reserves_usd_mn", re.compile(r"^Foreign Currency Reserves\s+([\d,]+)\s*$", re.M)),
    ("reserve_position_imf_usd_mn", re.compile(r"^Reserve position in the IMF\s+([\d,]+)\s*$", re.M)),
    ("sdrs_usd_mn", re.compile(r"^SDRs\s+([\d,]+)\s*$", re.M)),
    ("gold_usd_mn", re.compile(r"^Gold\s+([\d,]+)\s*$", re.M)),
    ("other_reserve_assets_usd_mn", re.compile(r"^Other Reserve Assets\s+([\d,]+)\s*$", re.M)),
]

RESERVE_BLOCK_WINDOW = 20  # lines; the detailed table's securities sub-breakdown needs ~11


def _parse_reserves(lines: list[str]) -> list[dict]:
    captions = []
    for i, line in enumerate(lines):
        m = RESERVES_QUICK_RE.search(line) or RESERVES_DETAILED_RE.search(line)
        if m:
            captions.append((i, m.group(1)))

    blocks = []
    for line_idx, as_of in captions:
        # Window starts AT this caption's own line, so an earlier block's rows
        # (e.g. the quick table's "Official Reserve Assets 6,450") are structurally
        # excluded from a later block's (the detailed table's "...6,881") window.
        window = "\n".join(lines[line_idx : line_idx + RESERVE_BLOCK_WINDOW])
        block = {"as_of": as_of}
        for key, pattern in RESERVE_FIELDS:
            m = pattern.search(window)
            if m:
                block[key] = int(m.group(1).replace(",", ""))
        if len(block) > 1:
            blocks.append(block)
    return blocks


def _reserves_latest(blocks: list[dict]) -> dict | None:
    if not blocks:
        return None
    return max(blocks, key=lambda b: datetime.strptime(b["as_of"], "%B %Y"))


# --- 4.x External Trade ---

TRADE_CAPTION_RE = re.compile(r"^(?:\d+\.\d+\s+)?External Trade\s*$")
TRADE_PERIOD_RE = re.compile(r"([A-Za-z]+\s*-\s*[A-Za-z]+)\s*\(USD mn\)")
TRADE_WINDOW = 40  # caption to Trade Balance row is ~19 lines; generous margin


def _row_numbers(line: str, count: int) -> tuple[str, list[float]] | None:
    """Split a line into (label, numbers) if it has exactly `count` numeric tokens.
    Handles the Trade Balance row's last two figures running together with no
    space, e.g. "(973,901.7)(1,746,178.3)" — NUM_TOKEN still tokenizes them apart."""
    matches = list(NUM_TOKEN.finditer(line))
    if len(matches) != count:
        return None
    label = line[: matches[0].start()].strip()
    if not label:
        return None
    return label, [_signed_num(m.group()) for m in matches]


def _parse_trade(lines: list[str]) -> dict | None:
    cap_idx = next((i for i, l in enumerate(lines) if TRADE_CAPTION_RE.match(l.strip())), None)
    if cap_idx is None:
        return None

    period = None
    for line in lines[cap_idx : cap_idx + 5]:
        m = TRADE_PERIOD_RE.search(line)
        if m:
            period = m.group(1).strip()
            break

    section = "exports"
    exports = imports = trade_balance = None
    exports_breakdown: list[dict] = []
    imports_breakdown: list[dict] = []
    for line in lines[cap_idx : cap_idx + TRADE_WINDOW]:
        row = _row_numbers(line.strip(), 4)
        if not row:
            continue
        label, (usd_2025, usd_2026, rs_2025, rs_2026) = row
        entry = {"usd_mn": {"2025": usd_2025, "2026": usd_2026}, "rs_mn": {"2025": rs_2025, "2026": rs_2026}}
        if label == "Exports":
            exports, section = entry, "exports"
        elif label == "Imports":
            imports, section = entry, "imports"
        elif label == "Trade Balance":
            trade_balance = entry
            break
        else:
            (exports_breakdown if section == "exports" else imports_breakdown).append({"label": label, **entry})

    if not (exports and imports and trade_balance):
        return None
    return {
        "period": period,
        "exports": exports,
        "exports_breakdown": exports_breakdown,
        "imports": imports,
        "imports_breakdown": imports_breakdown,
        "trade_balance": trade_balance,
    }


# The identity is arithmetic (exports - imports == trade balance), not a comparison
# between two independently-reported figures, so — unlike the WEI-wide ±1%
# provisional-revision tolerance the plan mentions for cross-edition comparisons —
# it should reconcile almost exactly. A tight absolute tolerance here is meant to
# catch genuine parse errors (wrong column picked up, row misaligned), not to
# paper over real data anomalies.
TRADE_IDENTITY_TOLERANCE = 0.5


def _validate_trade_identity(trade: dict) -> None:
    for currency in ("usd_mn", "rs_mn"):
        for year in ("2025", "2026"):
            exports = trade["exports"][currency][year]
            imports = trade["imports"][currency][year]
            balance = trade["trade_balance"][currency][year]
            diff = abs((exports - imports) - balance)
            if diff > TRADE_IDENTITY_TOLERANCE:
                raise ValueError(
                    f"trade balance identity failed for {currency} {year}: "
                    f"{exports} - {imports} = {exports - imports}, expected {balance} (diff {diff})"
                )


# --- 4.x Trade Indices (2010 = 100) ---

TRADE_INDICES_CAPTION_RE = re.compile(r"Trade Indices \(2010 = 100\)")
TRADE_INDICES_WINDOW = 25


def _row3(line: str) -> list[float] | None:
    nums = re.findall(r"-?[\d,]+\.\d+", line)
    if len(nums) == 3:
        return [float(n.replace(",", "")) for n in nums]
    return None


def _parse_trade_indices(lines: list[str]) -> dict | None:
    cap_idx = next((i for i, l in enumerate(lines) if TRADE_INDICES_CAPTION_RE.search(l)), None)
    if cap_idx is None:
        return None
    window = lines[cap_idx : cap_idx + TRADE_INDICES_WINDOW]

    def section(label: str) -> dict | None:
        idx = next((i for i, l in enumerate(window) if l.strip() == label), None)
        if idx is None:
            return None
        sub = {}
        for name, row_line in zip(("value", "quantity", "unit_value"), window[idx + 1 : idx + 4]):
            nums = _row3(row_line)
            if nums:
                sub[name] = {"year_ago": nums[0], "month_ago": nums[1], "latest": nums[2]}
        return sub or None

    total_exports = section("Total Exports")
    total_imports = section("Total Imports")
    terms_of_trade = None
    for l in window:
        if l.strip().startswith("Terms of Trade"):
            nums = _row3(l)
            if nums:
                terms_of_trade = {"year_ago": nums[0], "month_ago": nums[1], "latest": nums[2]}
            break

    if not (total_exports or total_imports or terms_of_trade):
        return None
    return {"total_exports": total_exports, "total_imports": total_imports, "terms_of_trade": terms_of_trade}


# --- 4.x Commodity Prices (best-effort — messiest table, chart noise interleaved) ---
#
# Rows here can appear BEFORE the "Commodity Prices" caption in the extracted text
# stream (the doc's z-scrambling again), so — unlike the other tables — we search
# for each row's own label directly across the whole page text rather than windowing
# forward from the caption. Crude Oil is skipped: its figures collide with a garbled
# duplicated fragment in the source text and aren't safely recoverable.


def _parse_commodities(text: str) -> dict | None:
    out: dict = {}

    m = re.search(r"^Tea Prices \(per kg\)\s+(.*)$", text, re.M)
    if m:
        nums = [t.group() for t in NUM_TOKEN.finditer(m.group(1))]
        if len(nums) == 6:
            v = [_signed_num(n) for n in nums]
            out["tea_per_kg"] = {
                "usd_2025": v[0], "usd_2026": v[1], "usd_pct_change": v[2],
                "lkr_2025": v[3], "lkr_2026": v[4], "lkr_pct_change": v[5],
            }

    m = re.search(r"^Colombo Tea Auctions\s+(.*)$", text, re.M)
    if m:
        nums = [t.group() for t in NUM_TOKEN.finditer(m.group(1))]
        if len(nums) == 4:
            v = [_signed_num(n) for n in nums]
            out["colombo_tea_auctions"] = {"usd_2025": v[0], "usd_2026": v[1], "lkr_2025": v[2], "lkr_2026": v[3]}

    # Rice/Sugar/Wheat: only the first 3 numbers (USD 2025, USD 2026, % change USD)
    # are unambiguous in the extracted text — a 4th trailing number is present but
    # its column identity (LKR % change vs. something else) isn't reliably inferable,
    # so it's dropped rather than guessed (per-row best-effort, see module note above).
    for label, key in (("Rice", "rice_per_mt"), ("Sugar", "sugar_per_mt"), ("Wheat", "wheat_per_mt")):
        m = re.search(rf"^{label} \(per MT\)\s+(.*)$", text, re.M)
        if m:
            nums = [t.group() for t in NUM_TOKEN.finditer(m.group(1))]
            if len(nums) >= 3:
                v = [_signed_num(n) for n in nums[:3]]
                out[key] = {"usd_2025": v[0], "usd_2026": v[1], "pct_change_usd": v[2]}

    return out or None


def parse_tables(payload: bytes) -> dict:
    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        text = "\n".join(_clean_ligatures(p.extract_text(layout=False) or "") for p in pdf.pages)
    lines = text.split("\n")

    out: dict = {}

    reserves = _parse_reserves(lines)
    if reserves:
        out["reserves"] = reserves
        latest = _reserves_latest(reserves)
        if latest:
            out["reserves_latest"] = latest

    trade = _parse_trade(lines)
    if trade:
        _validate_trade_identity(trade)  # raises on mismatch — a genuine parse error, not a data anomaly
        out["trade"] = trade

    trade_indices = _parse_trade_indices(lines)
    if trade_indices:
        out["trade_indices"] = trade_indices

    commodity_prices = _parse_commodities(text)
    if commodity_prices:
        out["commodity_prices"] = commodity_prices

    if not out:
        raise ValueError("cbsl_weekly parse_tables: no tables recognized — caption layout may have changed")
    return out
