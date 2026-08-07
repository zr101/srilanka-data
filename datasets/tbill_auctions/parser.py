"""Treasury T-bill auction press-release parser: prose regex over the PDF text.
Tenor derives from the ISIN prefix (LKA091.../182/364)."""

import io
import re

from pypdf import PdfReader

ISIN_RE = re.compile(r"\bLKA(\d{3})\w{5,9}\b")
YIELD_RE = re.compile(r"Weighted Average Yield Rates? of ([\d.]+%(?:[,\s]+(?:and\s+)?[\d.]+%)*)")
PCT_RE = re.compile(r"([\d.]+)%")
AMOUNT_RE = re.compile(r"Rs\.?\s*([\d,]+)\s*(?:mn|million)", re.I)


TENOR_LINE = re.compile(r"^(\d{2,3})$")
FIVE_NUMS = re.compile(r"^([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d.]+)\s+([\d.]+)$")
ISIN_LINE = re.compile(r"^LKA\w{9,12}$")
TOTAL_LINE = re.compile(r"^Total\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)$")


def parse_phase1(payload: bytes) -> dict:
    """Auction-day (phase-I) release: per tenor a 3-line group —
    tenor / 'offered bids accepted WAYR WAYR-last' / ISIN — then a Total row."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        lines = [l.strip() for l in (pdf.pages[0].extract_text() or "").split("\n") if l.strip()]
    results = []
    totals = None
    i = 0
    while i < len(lines):
        tm = TENOR_LINE.match(lines[i])
        if tm and i + 2 < len(lines):
            nm = FIVE_NUMS.match(lines[i + 1])
            im = ISIN_LINE.match(lines[i + 2])
            if nm and im:
                offered, bids, accepted = (int(nm.group(k).replace(",", "")) for k in (1, 2, 3))
                way, way_last = float(nm.group(4)), float(nm.group(5))
                if accepted > bids:
                    raise ValueError(f"tenor {tm.group(1)}: accepted > bids")
                if not 0 < way < 50:
                    raise ValueError(f"tenor {tm.group(1)}: WAYR {way} implausible")
                results.append(
                    {
                        "tenor_days": int(tm.group(1)),
                        "isin": lines[i + 2],
                        "offered_rs_mn": offered,
                        "bids_rs_mn": bids,
                        "accepted_rs_mn": accepted,
                        "way_pct": way,
                        "way_last_auction_pct": way_last,
                    }
                )
                i += 3
                continue
        tot = TOTAL_LINE.match(lines[i])
        if tot:
            totals = {k: int(tot.group(n).replace(",", "")) for n, k in ((1, "offered_rs_mn"), (2, "bids_rs_mn"), (3, "accepted_rs_mn"))}
        i += 1
    if not results:
        raise ValueError("no phase-I tenor groups parsed")
    if totals:
        for key in totals:
            if sum(r[key] for r in results) != totals[key]:
                raise ValueError(f"phase-I {key}: sum(tenors) != Total row")
    return {"phase": 1, "results": results, "totals": totals}


def parse_pdf(payload: bytes) -> dict:
    try:
        return parse_phase1(payload)
    except Exception:
        pass  # not a phase-I layout; fall through to phase-II prose
    text = " ".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(payload)).pages)
    text = re.sub(r"\s+", " ", text)
    isins = ISIN_RE.findall(text)
    yields_match = YIELD_RE.search(text)
    yields = [float(p) for p in PCT_RE.findall(yields_match.group(1))] if yields_match else []
    results = [
        {"tenor_days": int(tenor), "way_pct": way}
        for tenor, way in zip(isins, yields)
    ]
    if not results:
        raise ValueError("no ISIN/yield pairs parsed from auction release")
    for r in results:
        if not 0 < r["way_pct"] < 50:
            raise ValueError(f"implausible yield {r}")
    amounts = [int(a.replace(",", "")) for a in AMOUNT_RE.findall(text)]
    return {"results": results, "amounts_rs_mn": amounts, "text_excerpt": text[:400]}
