"""Treasury T-bill auction press-release parser: prose regex over the PDF text.
Tenor derives from the ISIN prefix (LKA091.../182/364)."""

import io
import re

from pypdf import PdfReader

ISIN_RE = re.compile(r"\bLKA(\d{3})\w{5,9}\b")
YIELD_RE = re.compile(r"Weighted Average Yield Rates? of ([\d.]+%(?:[,\s]+(?:and\s+)?[\d.]+%)*)")
PCT_RE = re.compile(r"([\d.]+)%")
AMOUNT_RE = re.compile(r"Rs\.?\s*([\d,]+)\s*(?:mn|million)", re.I)


def parse_pdf(payload: bytes) -> dict:
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
