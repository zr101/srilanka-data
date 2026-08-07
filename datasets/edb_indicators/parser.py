"""EDB annual Export Performance Indicators ebook (pypdf: clean columns here, unlike
CBSL's pdfplumber preference — no intra-number space artifacts in most tables).

Table 1 (totals): one page, labels followed by 'US $ Mn.' rows of yearly values.
The year count is edition-dependent (2023 ed. has 5 cols 2019-2023, 2024 ed. has 6
cols 2019-2024) — detected dynamically, not hardcoded.

parse_toc(): the front-matter TOC maps table numbers to the document's OWN page
numbering; that numbering is offset from the actual pypdf page index by a constant
that drifts per edition (front-matter length varies), so the offset is derived from
an anchor page (Table 1's own page, found by substring search) rather than assumed.

Table 13/15/17 extraction is additive (try/except in parse_pdf) — a failure there must
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
    """table-number string (verbatim as printed in the TOC, e.g. "21.01" not "21.1")
    -> 0-indexed pypdf page position. Expensive (~0.5s: an up-to-20-page TOC scan plus
    an up-to-50-page anchor scan) — callers that also need Table 13/15/17 etc. should
    compute this once and pass it in (see parse_table13/parse_table15/parse_table17's `toc` param)
    rather than each re-deriving it from raw bytes."""
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
            raw_map[tokens[0]] = int(tokens[-1])  # last occurrence wins if a table-no repeats (not seen in practice)
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


def parse_table13(payload: bytes, toc: dict[str, int] | None = None) -> dict:
    if toc is None:  # callers that already have a toc (e.g. parse_pdf) should pass it in — see parse_toc's docstring
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


# --- Table 15: Number of Exporters by Export Turnover -------------------------------
#
# Sector x turnover-band matrix, single page (found directly via TOC, like Table 17 —
# no multi-page scan needed). The band/column labels are z-order-scrambled to near the
# BOTTOM of the page's text stream (after the "Note :"/"Sources:" footer lines, nowhere
# near the data rows) — and that label line's own layout ISN'T stable across editions:
# the 2024 ed. has it as one line ("Total Over 100 100 to >50 50 to >35 35 to >1 1 to
# >0"), while the 2023 ed. splits it across two lines in reversed order, interleaved
# with the "Table - 15.1" caption. What IS stable is the underlying column order itself
# — verified by checking the "Total Exports" row's figures land in the same band order
# in both editions (see test_table15_five_year_edition for the pinned 2023 regression
# check). So the band order is hardcoded here rather than parsed from that unstable
# label line. No Σsectors==Total checksum on exporter counts either — the table's own
# footnote says a single exporter can count toward multiple sector rows AND the Total
# row by design (see _table15_pair below for the exact wording).
TABLE15_BANDS = ["total", "over_100", "100_to_50", "50_to_35", "35_to_1", "1_to_0"]
TABLE15_EXPECTED_ROWS = 11  # 10 sector rows + 1 "Total Exports" grand-total row

_TABLE15_TOKEN_RE = re.compile(r"^-$|^\d[\d,]*(?:\.\d+)?$")  # a number (with or without thousands-commas) or the "-" sentinel


def _table15_pair(exporters_tok: str, turnover_tok: str) -> dict:
    # A lone "-" is a valid sentinel meaning zero exporters/turnover in that band (not
    # missing data) — treated as 0, not null. Per the table's own footnote, a single
    # exporter can be counted in multiple sector rows AND in the Total row, so sector
    # "exporters" figures deliberately do NOT sum to the Total row's figure; no
    # checksum is enforced here for that reason.
    exporters = 0 if exporters_tok == "-" else int(exporters_tok.replace(",", ""))
    turnover = 0.0 if turnover_tok == "-" else float(turnover_tok.replace(",", ""))
    return {"exporters": exporters, "turnover_usd_mn": turnover}


def _parse_table15_rows(lines: list[str]) -> list[dict]:
    expected_tokens = 2 * len(TABLE15_BANDS)
    rows: list[dict] = []
    buffer: list[str] = []
    for line in lines:
        tokens = line.split()
        split_at = next((i for i, t in enumerate(tokens) if _TABLE15_TOKEN_RE.match(t)), None)
        if split_at is None:
            buffer.append(line)  # sector label wraps onto its own line(s) before the values line
            continue
        # Preserved verbatim, including "Plasitc" (a genuine typo in the source document
        # itself, e.g. "Chemical & Plasitc Products") — not silently corrected.
        sector = " ".join(buffer + tokens[:split_at]).strip()
        buffer = []
        value_tokens = tokens[split_at:]
        if len(value_tokens) != expected_tokens:
            raise ValueError(f"EDB Table 15: row {sector!r} has {len(value_tokens)} value tokens, expected {expected_tokens}")
        by_band = {band: _table15_pair(value_tokens[2 * i], value_tokens[2 * i + 1]) for i, band in enumerate(TABLE15_BANDS)}
        rows.append({"sector": sector, "by_band": by_band})
    return rows


def parse_table15(payload: bytes, toc: dict[str, int] | None = None) -> dict:
    if toc is None:  # callers that already have a toc (e.g. parse_pdf) should pass it in — see parse_toc's docstring
        toc = parse_toc(payload)
    page_idx = toc.get("15")
    if page_idx is None:
        raise ValueError("EDB TOC: table 15 page not found")

    text = PdfReader(io.BytesIO(payload)).pages[page_idx].extract_text() or ""
    if "NUMBER OF EXPORTERS BY EXPORT TURNOVER" not in text.upper():
        raise ValueError("EDB Table 15 page did not contain expected caption")

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    start = next((i for i, l in enumerate(lines) if l.startswith("Total Exports")), None)
    if start is None:
        raise ValueError("EDB Table 15: 'Total Exports' row not found")
    end = next((i for i, l in enumerate(lines) if i > start and l.startswith("Note")), None)
    if end is None:
        raise ValueError("EDB Table 15: 'Note' terminator not found")

    sectors = _parse_table15_rows(lines[start:end])
    if len(sectors) != TABLE15_EXPECTED_ROWS:
        raise ValueError(f"EDB Table 15: expected {TABLE15_EXPECTED_ROWS} rows (10 sectors + total), got {len(sectors)}")

    return {"bands": TABLE15_BANDS, "sectors": sectors}


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
        items_sum = sum(items.values())
        total = result[group]["total"]
        if total == 0:  # guard: a literal zero total would otherwise divide-by-zero below
            if items_sum != 0:
                raise ValueError(f"EDB Table 17 {group} checksum failed: sum={items_sum} vs total=0")
            continue
        diff_pct = abs(items_sum - total) / total * 100
        if diff_pct > TABLE17_CHECKSUM_TOLERANCE_PCT:
            raise ValueError(f"EDB Table 17 {group} checksum failed: sum={items_sum} vs total={total}")
    combined = result["goods"]["total"] + result["services"]["total"]
    if abs(combined - result["grand_total"]) > 1:
        raise ValueError(
            f"EDB Table 17 grand total mismatch: {result['goods']['total']}+{result['services']['total']} "
            f"!= {result['grand_total']}"
        )


def parse_table17(payload: bytes, toc: dict[str, int] | None = None) -> dict:
    if toc is None:  # callers that already have a toc (e.g. parse_pdf) should pass it in — see parse_toc's docstring
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


# --- Table 24.*/25.*: Exports by Market x Product ----------------------------------
#
# Both table families share literally the same page template: 24.<nn> is one page per
# destination MARKET (country), rows broken down by PRODUCT; 25.<nn> is one page per
# exported PRODUCT, rows broken down by MARKET. The only structural difference is
# which word ("Product"/"Market") labels the rows on a given page — everything else
# (layout, column shape, Total/Other-bucket handling, unit line) is identical, so one
# generic per-page parser (_parse_entity_page) serves both, parameterised by which
# label to expect in the row header (row_label) vs. which caption line names the page's
# own entity (the inverse label — a 24.* country page is captioned "Market :  ALBANIA",
# a 25.* product page "Product :  TEA (...)").
#
# Row shape: "<no> <name...> <year1..year5> <2024 % Share> <% Avg. Growth>" — 5 year
# values + share + growth = len(years)+2 trailing value tokens, always the LAST tokens
# on the (possibly multi-line-wrapped) row. A leading row number (1..40) is optional in
# the token stream (long names push it onto its own wrapped line, e.g. Albania's row 6
# "Coco Peat..." or China's row 35 "Made-up Textile Articles..."), so rows are scanned
# by matching the value-token tail from the END of the accumulated line buffer, not by
# splitting at the first numeric token (which would collide with the row number itself).
# The unnumbered "Other Products"/"Other Markets" catch-all bucket and the "Total :"
# row (sometimes numbered, sometimes not, per source) fall out of the exact same scan —
# classified afterwards by name, not parsed via separate logic.
#
# "-" sentinel: 0 in a value/share column (no export that year — a real figure), but
# None in the % Avg. Growth column (source's own footnote: growth is "insignificant"/
# not computable from a near-zero base, not a literal 0% rate).
#
# Occasionally a row is missing one of its value tokens outright (e.g. Albania's row 12
# "Petroleum Oils" has only 6 trailing value tokens where every other row has 7 — a
# genuine source artifact, not a line-wrap: verified directly against the live PDF, not
# just the task's transcription). Such rows are unrecoverable and skipped individually
# (mirrors Table 13's `_collapse_value_tokens` returning None) rather than corrupting
# the scan for every row after them.

_ENTITY_HEADER_RE = re.compile(r"^No\s+(Product|Market)\b")
_ENTITY_VALUE_TOK_RE = re.compile(r"^-$|^-?\d[\d,]*(?:\.\d+)?$")  # a number (with optional thousands-commas/decimals) or the "-" sentinel
_ENTITY_ROWNUM_RE = re.compile(r"^\d{1,2}$")  # observed row numbers only ever run 1..40
_TABLE_CAPTION_RE = re.compile(r"^Table\s*:\s*(\S+)")
_MERCH_SHARE_PREFIX = "% Share to Total Merchandise Exports"


def _entity_value(tok: str) -> float:
    return 0.0 if tok == "-" else float(tok.replace(",", ""))


def _entity_growth(tok: str) -> float | None:
    return None if tok == "-" else float(tok.replace(",", ""))


def _scan_entity_records(lines: list[str], expected: int) -> list[tuple[str | None, list[str], list[str]]]:
    """Yields (row_num_or_None, name_tokens, value_tokens) for every numbered row, the
    optional Other-bucket line, and the Total line found in `lines`. `expected` is
    len(years)+2 — the fixed trailing value-token count every one of those rows has."""
    records: list[tuple[str | None, list[str], list[str]]] = []
    buffer: list[str] = []
    for line in lines:
        tokens = line.split()
        if not tokens:
            continue
        combined = buffer + tokens
        row_num = combined[0] if _ENTITY_ROWNUM_RE.match(combined[0]) else None
        rest = combined[1:] if row_num is not None else combined
        if len(rest) >= expected and all(_ENTITY_VALUE_TOK_RE.match(t) for t in rest[-expected:]):
            records.append((row_num, rest[: -expected], rest[-expected:]))
            buffer = []
            continue
        # Not (yet) a complete row — distinguish "name still wrapping onto more lines"
        # (no values seen at all yet) from "a malformed row with only SOME of its
        # expected values present" (the Petroleum Oils case above): the latter can
        # never complete by buffering further, so drop it and resync on the next line
        # rather than let it swallow every row after it.
        tail_run = 0
        for t in reversed(rest):
            if _ENTITY_VALUE_TOK_RE.match(t):
                tail_run += 1
            else:
                break
        buffer = combined if tail_run == 0 else []
    return records


def _classify_entity_records(
    records: list[tuple[str | None, list[str], list[str]]], years: list[int], row_label: str
) -> tuple[list[dict], dict | None, dict | None]:
    rows: list[dict] = []
    other: dict | None = None
    total: dict | None = None
    other_name = f"Other {row_label}s"
    for row_num, name_tokens, value_tokens in records:
        name = " ".join(name_tokens).strip().rstrip(":").strip()
        if not name:
            continue
        record = {
            "no": int(row_num) if row_num is not None else None,
            "name": name,
            "values_usd": {str(y): _entity_value(t) for y, t in zip(years, value_tokens)},
            "share_pct": _entity_value(value_tokens[len(years)]),
            "avg_growth_pct": _entity_growth(value_tokens[len(years) + 1]),
        }
        if name.lower() == "total":
            total = record
        elif name == other_name:
            other = record
        else:
            rows.append(record)
    return rows, other, total


def _parse_entity_page(pages, page_idx: int, row_label: str, table_id: str | None = None) -> dict:
    """Parses one 24.*/25.* page. `row_label` is "Product" for a 24.* (country) page or
    "Market" for a 25.* (product) page — i.e. what the row header itself says, the
    OPPOSITE of the page's own entity caption (see banner comment above)."""
    if not (0 <= page_idx < len(pages)):
        raise ValueError(f"EDB entity page index {page_idx} out of range")
    text = pages[page_idx].extract_text() or ""
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    if table_id is not None:
        caption = next((m.group(1) for l in lines if (m := _TABLE_CAPTION_RE.match(l))), None)
        if caption != table_id:
            raise ValueError(f"EDB entity page {page_idx}: caption {caption!r} != expected table id {table_id!r}")

    header_idx = next((i for i, l in enumerate(lines) if _ENTITY_HEADER_RE.match(l)), None)
    if header_idx is None:
        raise ValueError(f"EDB entity page {page_idx}: header row not found")
    header_label = _ENTITY_HEADER_RE.match(lines[header_idx]).group(1)
    if header_label != row_label:
        raise ValueError(f"EDB entity page {page_idx}: expected row label {row_label!r}, found {header_label!r}")

    years = [int(y) for y in re.findall(r"20\d{2}", lines[header_idx])][:-1]  # header repeats the latest year for "2024 % Share" — drop that dup
    if not (3 <= len(years) <= 10):
        raise ValueError(f"EDB entity page {page_idx}: implausible year header: {years}")

    sources_idx = next((i for i in range(header_idx + 1, len(lines)) if lines[i].startswith("Sources")), None)
    if sources_idx is None:
        raise ValueError(f"EDB entity page {page_idx}: 'Sources' terminator not found")
    body = [l for l in lines[header_idx + 1 : sources_idx] if l not in ("Share", "% Avg.", "Growth")]  # header-wrap fragments

    merch_idx = next((i for i, l in enumerate(body) if l.startswith(_MERCH_SHARE_PREFIX)), None)
    if merch_idx is None:
        raise ValueError(f"EDB entity page {page_idx}: merchandise-share row not found")
    merch_tokens = body[merch_idx].split()[-len(years) :]
    if len(merch_tokens) != len(years) or not all(_ENTITY_VALUE_TOK_RE.match(t) for t in merch_tokens):
        raise ValueError(f"EDB entity page {page_idx}: merchandise-share row malformed: {body[merch_idx]!r}")
    merchandise_share_pct = {str(y): _entity_value(t) for y, t in zip(years, merch_tokens)}

    row_lines = body[:merch_idx] + body[merch_idx + 1 :]
    expected = len(years) + 2
    records = _scan_entity_records(row_lines, expected)
    rows, other, total = _classify_entity_records(records, years, row_label)
    if total is None:
        raise ValueError(f"EDB entity page {page_idx}: Total row not found")

    entity_label = "Market" if row_label == "Product" else "Product"  # this page's own entity caption uses the OTHER label
    entity_idx = next((i for i, l in enumerate(lines) if l.startswith(f"{entity_label} :")), None)
    if entity_idx is None:
        raise ValueError(f"EDB entity page {page_idx}: {entity_label} caption not found")
    entity = re.sub(r"\s+", " ", lines[entity_idx].split(":", 1)[1]).strip()
    if not entity:
        raise ValueError(f"EDB entity page {page_idx}: empty {entity_label} caption")

    unit_line = next((l for l in lines if l.startswith("Value in US$")), None)
    if unit_line is None:
        raise ValueError(f"EDB entity page {page_idx}: unit line not found")
    if "Thousand" in unit_line:
        multiplier = 1
    elif "Million" in unit_line:
        multiplier = 1000  # normalize everything to USD Thousands, this page's own smaller-magnitude unit
    else:
        raise ValueError(f"EDB entity page {page_idx}: unrecognized unit {unit_line!r}")
    for record in rows + ([other] if other else []) + [total]:
        record["values_usd"] = {y: v * multiplier for y, v in record["values_usd"].items()}

    return {
        "entity": entity,
        "years": years,
        "unit": "USD Thousands",
        "rows": rows,
        "other": other,
        "total": total,
        "merchandise_share_pct": merchandise_share_pct,
    }


_TOC_COUNTRY_RE = re.compile(r"^24\.\d+$")
_TOC_PRODUCT_RE = re.compile(r"^25\.\d+$")


def _parse_entity_batch(payload: bytes, toc: dict[str, int] | None, toc_pattern: re.Pattern, row_label: str) -> dict:
    if toc is None:  # callers that already have a toc (e.g. parse_pdf) should pass it in — see parse_toc's docstring
        toc = parse_toc(payload)
    pages = PdfReader(io.BytesIO(payload)).pages
    result: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for table_id, page_idx in toc.items():
        if not toc_pattern.match(table_id):
            continue
        try:
            page = _parse_entity_page(pages, page_idx, row_label, table_id=table_id)
        except Exception as err:  # noqa: BLE001 — a single bad/blank page (this fixture has ~260 still-blank
            # ones; production editions can have genuine one-off layout quirks) must never cost the other
            # ~99/~164 good entities in the same batch, so this is deliberately broader than the ValueError
            # this module's other parsers raise-and-catch — anything short of a KeyboardInterrupt is contained here.
            errors[table_id] = str(err)
            continue
        result[page["entity"]] = page
    if errors:
        result["_errors"] = errors
    return result


def parse_countries(payload: bytes, toc: dict[str, int] | None = None) -> dict[str, dict]:
    """Table 24.*: one page per destination market/country, rows broken down by product."""
    return _parse_entity_batch(payload, toc, _TOC_COUNTRY_RE, "Product")


def parse_products(payload: bytes, toc: dict[str, int] | None = None) -> dict[str, dict]:
    """Table 25.*: one page per exported product, rows broken down by destination market."""
    return _parse_entity_batch(payload, toc, _TOC_PRODUCT_RE, "Market")


def parse_pdf(payload: bytes) -> dict:
    clean = parse_text(find_table_text(payload))  # core contract; must keep raising on failure
    # Computed once and threaded into both table parsers below — parse_toc is the
    # expensive part of each (~0.5s: an up-to-20-page TOC scan + up-to-50-page anchor
    # scan), and re-deriving it independently per table would scale linearly as more
    # EDB tables (15, 21.*, 24.*, 25.*) are added on top of this same pattern.
    try:
        toc = parse_toc(payload)
    except ValueError:
        toc = None  # each table parser below falls back to deriving it independently
    try:
        clean["table13"] = parse_table13(payload, toc=toc)
    except ValueError as err:
        clean["_table13_error"] = str(err)
    try:
        clean["table15"] = parse_table15(payload, toc=toc)
    except ValueError as err:
        clean["_table15_error"] = str(err)
    try:
        clean["table17"] = parse_table17(payload, toc=toc)
    except ValueError as err:
        clean["_table17_error"] = str(err)
    try:
        clean["countries"] = parse_countries(payload, toc=toc)
    except ValueError as err:
        clean["_countries_error"] = str(err)
    try:
        clean["products"] = parse_products(payload, toc=toc)
    except ValueError as err:
        clean["_products_error"] = str(err)
    return clean


def rebuild(payload: bytes, _existing: dict) -> dict:
    clean = dict(_existing)
    clean.update(parse_pdf(payload))
    return clean
