"""EDB annual Export Performance Indicators ebook (pypdf: clean columns here, unlike
CBSL's pdfplumber preference — no intra-number space artifacts in most tables).

Table 1 (totals): one page, labels followed by 'US $ Mn.' rows of yearly values.
The year count is edition-dependent (2023 ed. has 5 cols 2019-2023, 2024 ed. has 6
cols 2019-2024) — detected dynamically, not hardcoded.

parse_toc(): the front-matter TOC maps table numbers to the document's OWN page
numbering; that numbering is offset from the actual pypdf page index by a constant
that drifts per edition (front-matter length varies), so the offset is derived from
an anchor page (Table 1's own page, found by substring search) rather than assumed.

Table 13/17 extraction is additive (try/except in parse_pdf) — a failure there must
never cost Table 1's core contract.
"""

import io
import re

from pypdf import PdfReader

LABELS = {
    "total_usd_mn": "Total Exports",
    "merchandise_usd_mn": "Total Merchandise Exports",
    "services_usd_mn": "Total Services Exports",
}
NUM_RE = re.compile(r"\d{1,3}(?:,\d{3})*")


def find_table_text(payload: bytes) -> str:
    for page in PdfReader(io.BytesIO(payload)).pages:
        text = page.extract_text() or ""
        if "Total Merchandise Exports" in text:
            return text
    raise ValueError("EDB totals table page not found")


def parse_text(text: str) -> dict:
    desc = text.find("Description")
    if desc < 0:
        raise ValueError("EDB table header not found")
    # Year-column count is edition-dependent (5 cols in the 2023 ed., 6 in 2024) —
    # take whatever the header actually has, bounded to something sane so a genuine
    # parse failure (e.g. layout change) still gets rejected.
    years = [int(y) for y in re.findall(r"20\d{2}", text[desc : desc + 200])]
    if not (3 <= len(years) <= 10):
        raise ValueError(f"EDB years header implausible: {years}")

    result: dict = {"years": years}
    for key, label in LABELS.items():
        i = text.find(label)
        if i < 0:
            raise ValueError(f"label missing: {label}")
        usd = text.find("US $ Mn", i)
        if usd < 0:
            raise ValueError(f"US $ row missing after: {label}")
        values = [int(n.replace(",", "")) for n in NUM_RE.findall(text[usd : usd + 300])[: len(years)]]
        if len(values) < len(years):
            raise ValueError(f"incomplete series for {label}: {values}")
        result[key] = values
    return result


# --- TOC-driven page map ---------------------------------------------------------
#
# Every TOC page repeats a "TABLE/ GRAPH \n NO \n  \n PAGE" header — that's the
# reliable per-page marker used to collect TOC pages (bounded scan; front matter is
# always a handful of pages). Each entry line is "<table-no> <title...> <page>";
# split on whitespace and take first/last tokens rather than one complex regex,
# since titles can themselves contain digits (year ranges like "2019-2024").

TOC_SCAN_PAGES = 20  # front matter is a handful of pages; generous margin
ANCHOR_SCAN_PAGES = 50  # Table 1 has always been seen well within the first ~15


def parse_toc(payload: bytes) -> dict[str, int]:
    pages = PdfReader(io.BytesIO(payload)).pages

    raw_map: dict[str, int] = {}
    for page in pages[:TOC_SCAN_PAGES]:
        text = page.extract_text() or ""
        if "TABLE/ GRAPH" not in text:
            continue
        for line in text.split("\n"):
            tokens = line.split()
            if len(tokens) < 3:
                continue
            if not re.match(r"^\d+(?:\.\d+)?$", tokens[0]):
                continue
            if not re.match(r"^\d{1,3}$", tokens[-1]):
                continue
            raw_map[tokens[0]] = int(tokens[-1])
    if "1" not in raw_map:
        raise ValueError("EDB TOC: table 1 entry not found")

    anchor_idx = next(
        (i for i, p in enumerate(pages[:ANCHOR_SCAN_PAGES]) if "Total Merchandise Exports" in (p.extract_text() or "")),
        None,
    )
    if anchor_idx is None:
        raise ValueError("EDB TOC: table 1 anchor page not found")

    offset = anchor_idx - raw_map["1"]
    return {tid: toc_page + offset for tid, toc_page in raw_map.items() if 0 <= toc_page + offset < len(pages)}


# --- Table 13: Disaggregated Export Performance -----------------------------------
#
# Flat list, deliberately WITHOUT category/sub-item hierarchy: the 2023 edition marks
# sub-items with a leading '-'/'--' (stripped below, cosmetic only), but the 2024
# edition has no such marker at all — indentation isn't preserved by pypdf's text
# extraction either. Inferring which of ~20 rows are category headers vs sub-items
# from names alone would be guesswork (Table 13 has more sectors than the Table 14
# hint list), so hierarchy — and the category-sum checksum it would enable — is
# skipped. The grand "Total" row is captured for reference only.
#
# Numbers occasionally arrive split across two whitespace-tokens by a line-wrap
# artifact (e.g. "649. 67", "58 4.05", "27.1 1") — detected by needing one merge to
# reach the expected column count. Rare Excel-corruption artifacts in the source
# (e.g. "#BEZUG!" replacing a value, "#NAME?" replacing a description) make a row
# unrecoverable; those rows are skipped rather than guessed (best-effort, same
# philosophy as the rest of this codebase's additive table parsers).

TABLE13_PAGE_SCAN_CAP = 15
_TABLE13_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_TABLE13_PLACEHOLDER_RE = re.compile(r"^-$|^\.{2,}$")  # '-' (2024 ed.) / '...' (2023 ed.) both mean n/a


def _looks_numeric(tok: str) -> bool:
    return bool(_TABLE13_NUM_RE.match(tok)) or bool(_TABLE13_PLACEHOLDER_RE.match(tok))


def _table13_value(tok: str) -> float | None:
    return None if _TABLE13_PLACEHOLDER_RE.match(tok) else float(tok)


def _merged_split_number(a: str, b: str) -> str | None:
    """Recombine a number that a line-wrap artifact split across two tokens. Deliberately
    directional (not "any concatenation that happens to parse") — values here are
    consistently formatted to 2 decimal places, which is what makes each case
    unambiguous: an incomplete "649." can only be completed by trailing digits; a bare
    integer "58" followed by "4.05" can only be a split integer PART of one number
    (two genuinely separate real columns are never int-then-decimal by convention); and
    a complete decimal like "27.1" can only be missing exactly one more digit ("1") to
    reach 2 places — a 2-digit second token there (as in the false-positive
    "616.08"+"58") is instead a genuine adjacent value and must NOT be merged."""
    if a.endswith(".") and re.fullmatch(r"\d+", b):
        return a + b  # "649." + "67" -> "649.67"
    if re.fullmatch(r"\d+", a) and re.fullmatch(r"\d+\.\d+", b):
        return a + b  # "58" + "4.05" -> "584.05"
    if re.fullmatch(r"\d+\.\d", a) and re.fullmatch(r"\d", b):
        return a + b  # "27.1" + "1" -> "27.11"
    return None


def _collapse_value_tokens(tokens: list[str], expected: int) -> list[str] | None:
    tokens = list(tokens)
    i = 0
    while len(tokens) > expected and i < len(tokens) - 1:
        merged = _merged_split_number(tokens[i], tokens[i + 1])
        if merged is not None:
            tokens[i : i + 2] = [merged]
            i = 0
        else:
            i += 1
    if len(tokens) == expected - 1:
        tokens.append("...")  # trailing avg-growth occasionally omitted in the source (e.g. "Tomato")
    if len(tokens) != expected or not all(_looks_numeric(t) for t in tokens):
        return None
    return tokens


def _clean_table13_lines(text: str, years: list[int] | None) -> tuple[list[str], list[int] | None]:
    lines = []
    for raw in text.split("\n"):
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("Sri Lanka Export Development Board"):
            continue
        if re.match(r"^Table\s*-\s*13\.\d+$", stripped):
            continue
        if stripped.startswith("Description") and re.search(r"(?:19|20)\d{2}", stripped):
            if years is None:
                years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", stripped)]
            continue
        if stripped == "Growth":  # header wraps "% Avg." / "Growth" onto two lines in some editions
            continue
        if re.match(r"^\d+\.\s*DISAGGREGATED", stripped, re.I):
            continue
        if re.match(r"^Value in US\$\s*Millions?$", stripped, re.I):
            continue
        lines.append(stripped)
    return lines, years


def _parse_table13_rows(lines: list[str], years: list[int]) -> tuple[list[dict], dict | None]:
    expected = len(years) + 1  # 9 year columns + 1 avg-growth column
    rows: list[dict] = []
    total: dict | None = None
    buffer: list[str] = []
    for line in lines:
        if not re.search(r"\d", line):
            buffer.append(line)  # description wraps onto its own line(s) before the values line
            continue
        tokens = line.split()
        split_at = next((i for i, t in enumerate(tokens) if _looks_numeric(t)), None)
        if split_at is None:
            buffer.append(line)
            continue
        description = re.sub(r"^-+", "", " ".join(buffer + tokens[:split_at])).strip()
        buffer = []
        if not description:
            continue
        value_tokens = _collapse_value_tokens(tokens[split_at:], expected)
        if value_tokens is None:
            continue  # unrecoverable row (e.g. an embedded "#BEZUG!" Excel-error artifact) — skip
        values = {str(y): _table13_value(t) for y, t in zip(years, value_tokens[:-1])}
        record = {"description": description, "values": values, "avg_growth_pct": _table13_value(value_tokens[-1])}
        if description == "Total":
            total = {"values": values, "avg_growth_pct": record["avg_growth_pct"]}
        else:
            rows.append(record)
    return rows, total


def parse_table13(payload: bytes) -> dict:
    toc = parse_toc(payload)
    start = toc.get("13")
    if start is None:
        raise ValueError("EDB TOC: table 13 page not found")

    pages = PdfReader(io.BytesIO(payload)).pages
    years: list[int] | None = None
    all_lines: list[str] = []
    found_total = False
    for idx in range(start, min(start + TABLE13_PAGE_SCAN_CAP, len(pages))):
        text = pages[idx].extract_text() or ""
        page_lines, years = _clean_table13_lines(text, years)
        if page_lines and re.match(r"^\d{1,3}$", page_lines[-1]):
            page_lines = page_lines[:-1]  # trailing page-number footer
        all_lines.extend(page_lines)
        if any(re.match(r"^Total\s", l) for l in page_lines):
            found_total = True
            break
    if not years or not (3 <= len(years) <= 15):
        raise ValueError(f"EDB Table 13: implausible or missing year header: {years}")
    if not found_total:
        raise ValueError("EDB Table 13: grand Total row not found within page scan window")

    rows, total = _parse_table13_rows(all_lines, years)
    if total is None:
        raise ValueError("EDB Table 13: grand Total row not parsed")
    if len(rows) < 20:
        raise ValueError(f"EDB Table 13: only {len(rows)} rows parsed, expected many more")
    return {"years": years, "rows": rows, "total": total}


# --- Table 17: Export Forecast -----------------------------------------------------
#
# Single page, two labelled groups (goods / services line items) each with their own
# "Total ..." checksum row, plus a grand total combining both.

_SECTION_GOODS_RE = re.compile(r"^Exports of Merchandi[sz]e\s*/\s*Goods", re.I)
_SECTION_SERVICES_RE = re.compile(r"^Exports of Services", re.I)
_ROW_RE = re.compile(r"^(.+?)\s+([\d,]+(?:\.\d+)?)\s*$")
TABLE17_CHECKSUM_TOLERANCE_PCT = 2.0


def _table17_value(raw: str) -> int:
    v = raw.replace(",", "")
    if re.fullmatch(r"\d+\.\d{3}", v):
        # Source typo: a lone "X.YYY" value (e.g. "1.978" for Transport & Logistics) where every
        # other Table 17 figure is a whole US$ Mn integer — a stray "." used as a thousands
        # separator instead of ",". Left alone this would parse ~1000x too small.
        v = v.replace(".", "")
    return int(round(float(v)))


def _validate_table17(result: dict) -> None:
    for group in ("goods", "services"):
        items = {k: v for k, v in result[group].items() if k != "total"}
        total = result[group]["total"]
        diff_pct = abs(sum(items.values()) - total) / total * 100
        if diff_pct > TABLE17_CHECKSUM_TOLERANCE_PCT:
            raise ValueError(f"EDB Table 17 {group} checksum failed: sum={sum(items.values())} vs total={total}")
    combined = result["goods"]["total"] + result["services"]["total"]
    if abs(combined - result["grand_total"]) > 1:
        raise ValueError(
            f"EDB Table 17 grand total mismatch: {result['goods']['total']}+{result['services']['total']} "
            f"!= {result['grand_total']}"
        )


def parse_table17(payload: bytes) -> dict:
    toc = parse_toc(payload)
    page_idx = toc.get("17")
    if page_idx is None:
        raise ValueError("EDB TOC: table 17 page not found")

    text = PdfReader(io.BytesIO(payload)).pages[page_idx].extract_text() or ""
    if "EXPORT FORECAST" not in text.upper():
        raise ValueError("EDB Table 17 page did not contain expected caption")

    goods: dict[str, int] = {}
    services: dict[str, int] = {}
    goods_total = services_total = grand_total = None
    section = None
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if _SECTION_GOODS_RE.match(line):
            section = "goods"
            continue
        if _SECTION_SERVICES_RE.match(line):
            section = "services"
            continue
        m = _ROW_RE.match(line)
        if not m:
            continue
        label = re.sub(r"\s+", " ", m.group(1)).strip()
        value = _table17_value(m.group(2))
        if label.startswith("Total") and "&" in label:
            grand_total = value
            break
        elif label.startswith("Total Merchandi"):
            goods_total = value
        elif label.startswith("Total Services"):
            services_total = value
        elif section == "goods":
            goods[label] = value
        elif section == "services":
            services[label] = value

    if goods_total is None or services_total is None or grand_total is None:
        raise ValueError("EDB Table 17: totals not fully captured")

    result = {"goods": {**goods, "total": goods_total}, "services": {**services, "total": services_total}, "grand_total": grand_total}
    _validate_table17(result)
    return result


def parse_pdf(payload: bytes) -> dict:
    clean = parse_text(find_table_text(payload))  # core contract; must keep raising on failure
    try:
        clean["table13"] = parse_table13(payload)
    except ValueError as err:
        clean["_table13_error"] = str(err)
    try:
        clean["table17"] = parse_table17(payload)
    except ValueError as err:
        clean["_table17_error"] = str(err)
    return clean
