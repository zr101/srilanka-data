"""CBSL Daily Price Report — wholesale and retail food prices.

Two extractions:

* **page 2** — the substantive table: ~25 commodities against five market
  columns (Pettah/Dambulla wholesale, Pettah/Dambulla/Narahenpita retail),
  each with yesterday and today.
* **page 1** — the highlight blocks, which carry the *reason* a price moved
  ("favourable supply from Nuwara Eliya"), something no other source here has.

The one real trap is that numbers arrive pre-split: pdfplumber emits "128.00"
as the two words '1' and '28.00'. That is a kerning artifact rather than the
z-order scrambling the DEI suffers — the fragments are horizontally adjacent
(a 0.1pt gap), so they are rejoined on that gap and then assigned to a market
column by x-position. Splitting on whitespace instead would silently turn
Rs 128.00 into Rs 1.
"""

import re

import pdfplumber

# Fragments closer than this are one number that the extractor split.
JOIN_GAP = 1.5
MISSING = {"n.a.", "n.a", "-", "…", "..."}
NUMBER = re.compile(r"^[\d,]+\.\d{2}$")


def _tokens(words: list[dict]) -> list[dict]:
    """Merge horizontally adjacent word fragments back into whole tokens."""
    out: list[dict] = []
    for word in sorted(words, key=lambda w: w["x0"]):
        if out and word["x0"] - out[-1]["x1"] < JOIN_GAP:
            out[-1]["text"] += word["text"]
            out[-1]["x1"] = word["x1"]
        else:
            out.append({"text": word["text"], "x0": word["x0"], "x1": word["x1"]})
    return out


def _rows(page) -> list[list[dict]]:
    """Group a page's words into rows by their vertical centre."""
    rows: dict[int, list[dict]] = {}
    for word in page.extract_words():
        rows.setdefault(round((word["top"] + word["bottom"]) / 4), []).append(word)
    return [_tokens(ws) for _, ws in sorted(rows.items())]


def _num(text: str) -> float | None:
    if text in MISSING or not NUMBER.match(text):
        return None
    return float(text.replace(",", ""))


def parse_table(page) -> dict:
    """The wholesale/retail table.

    Column positions are derived from the data rather than the header. Monday
    editions compare against "Last Friday" instead of "Yesterday" and split the
    period labels across two lines instead of interleaving them on one, so any
    header-wording rule breaks roughly one day in five. The value columns
    themselves are stable, so they are recovered by clustering the x-centres of
    every numeric cell in the table and matching the count to 2x the markets.
    """
    rows = _rows(page)

    market_row = next(
        (r for r in rows if sum(t["text"] in ("Pettah", "Dambulla", "Narahenpita") for t in r) >= 3),
        None,
    )
    if market_row is None:
        raise ValueError("price table: no market header row")
    markets = [t["text"] for t in market_row if t["text"] in ("Pettah", "Dambulla", "Narahenpita")]
    # Wholesale markets come first, then retail; the split is where the market
    # sequence restarts, which survives a market being added on either side.
    split = next((i for i in range(1, len(markets)) if markets[i] in markets[:i]), len(markets))

    def cells(row):
        return [t for t in row if NUMBER.match(t["text"]) or t["text"] in MISSING]

    data_rows = [r for r in rows if len(cells(r)) >= 4]
    if not data_rows:
        raise ValueError("price table: no data rows")

    centres = sorted((c["x0"] + c["x1"]) / 2 for r in data_rows for c in cells(r))
    clusters: list[list[float]] = []
    for centre in centres:
        if clusters and centre - clusters[-1][-1] <= 12:
            clusters[-1].append(centre)
        else:
            clusters.append([centre])
    if len(clusters) != len(markets) * 2:
        raise ValueError(
            f"price table: {len(clusters)} value columns for {len(markets)} markets"
        )

    columns = []
    for i, cluster in enumerate(clusters):
        market = markets[i // 2]
        columns.append(
            {
                "market": market,
                "basis": "wholesale" if i // 2 < split else "retail",
                "when": "previous" if i % 2 == 0 else "today",
                "centre": sum(cluster) / len(cluster),
            }
        )

    # Header wording is metadata only: "Yesterday" most days, "Last Friday" on Mondays.
    header_text = " ".join(t["text"] for r in rows[:12] for t in r)
    # _tokens joins the tightly-kerned "Last"+"Friday" into one token.
    compares_to = "last Friday" if "LastFriday" in header_text.replace(" ", "") else "yesterday"

    items, section = [], None
    for row in rows:
        values = cells(row)
        letters = re.sub(r"[^A-Za-z]", "", " ".join(t["text"] for t in row))
        if len(row) > 3 and all(len(t["text"]) == 1 for t in row) and letters:
            section = letters.title()
            continue
        if len(values) < 4:
            continue
        label = " ".join(t["text"] for t in row if t not in values)
        unit = re.search(r"(Rs\./\S+)", label)
        name = label.replace(unit.group(1), "").strip() if unit else label.strip()
        if not name:
            continue

        prices: dict = {}
        for value in values:
            centre = (value["x0"] + value["x1"]) / 2
            column = min(columns, key=lambda c: abs(c["centre"] - centre))
            prices.setdefault(f"{column['basis']}_{column['market'].lower()}", {})[
                column["when"]
            ] = _num(value["text"])
        items.append(
            {"item": name, "unit": unit.group(1) if unit else None, "section": section, "prices": prices}
        )
    if not items:
        raise ValueError("price table: no commodity rows")
    return {"markets": markets[:split], "compares_to": compares_to, "items": items}


# The commodity name and its direction verb are often split across two lines
# ("Wholesale price of Kelawalla" / "declined in Peliyagoda..."), so the
# heading is matched on the name alone and the direction read from the block's
# accumulated commentary. Requiring both on one line silently dropped every
# wrapped fish block.
HIGHLIGHT = re.compile(
    r"(?:Wholesale price|Price) of ([A-Z][A-Za-z ()']*?)"
    r"(?=\s+(?:increased|declined|remained)\b|\s+Rs\./|\s*$)"
)
DIRECTION = re.compile(r"\b(increased|declined|remained)\b", re.I)
MOVE = re.compile(r"([A-Za-z][A-Za-z' ]*?)\s*:\s*([\d,]+\.\d{2})\s+([\d,]+\.\d{2})")
CATEGORIES = ("Vegetables", "Fish", "Other", "Coconut", "Rice", "Fruits", "Meat", "Egg")

# A price line sits within ~25pt of its commodity heading in a well-formed
# report. Some editions (2026-08-05) interleave two columns' characters into
# one unreadable line — the DEI's z-order problem appearing intermittently —
# which destroys a heading and would otherwise hand its price rows to the
# commodity above. Anything further than this is orphaned and dropped.
MAX_BLOCK_GAP = 40


def parse_highlights(page) -> list[dict]:
    """Page-1 movers: commodity, market, yesterday → today, and the stated cause.

    Blocks are associated by vertical order — a price line belongs to the most
    recent commodity heading above it.
    """
    lines = sorted(page.extract_text_lines(), key=lambda l: l["top"])
    highlights: list[dict] = []
    category = None
    heading_top = None
    orphans = 0
    for line in lines:
        text = line["text"]
        if line["x0"] < 70:
            hit = next((c for c in CATEGORIES if text.startswith(c)), None)
            if hit:
                category = hit
        found = HIGHLIGHT.search(text)
        if found:
            heading_top = line["top"]
            highlights.append(
                {
                    "item": found.group(1).strip(),
                    "direction": None,
                    "category": category,
                    "moves": [],
                    "commentary": [text],
                }
            )
            continue
        if not highlights or heading_top is None:
            continue
        if line["top"] - heading_top > MAX_BLOCK_GAP:
            orphans += len(MOVE.findall(text))
            continue
        for market, yesterday, today in MOVE.findall(text):
            # Commentary runs into the same line, so keep only the trailing
            # word before the colon — the market name.
            name = market.strip().split()[-1] if market.strip() else ""
            if name and name[0].isupper():
                highlights[-1]["moves"].append(
                    {
                        "market": name,
                        "previous": _num(yesterday),
                        "today": _num(today),
                    }
                )
        highlights[-1]["commentary"].append(text)
    for h in highlights:
        h["commentary"] = " ".join(h["commentary"])
        verb = DIRECTION.search(h["commentary"])
        h["direction"] = verb.group(1).lower() if verb else None
    return [h for h in highlights if h["moves"]], orphans


def parse_pdf(payload: bytes) -> dict:
    import io

    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        first = pdf.pages[0].extract_text() or ""
        date = re.search(r"Developments\s*-\s*(\d{1,2}\s+\w+\s+\d{4})", first)
        table = parse_table(pdf.pages[1]) if len(pdf.pages) > 1 else {"markets": [], "items": []}
        highlights, orphans = parse_highlights(pdf.pages[0])
    notes = []
    if orphans:
        notes.append(
            f"{orphans} highlight price row(s) dropped: no commodity heading within "
            f"{MAX_BLOCK_GAP}pt, usually a column-interleaved line in this edition"
        )
    return {
        "report_date_text": date.group(1) if date else None,
        "markets": table["markets"],
        "compares_to": table.get("compares_to"),
        "items": table["items"],
        "highlights": highlights,
        "notes": notes,
    }
