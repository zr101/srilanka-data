"""EDB annual Export Performance Indicators: totals table (one page of a 340-page
ebook). pypdf reads it; labels are followed by 'US $ Mn.' rows of 6 yearly values."""

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
    years = [int(y) for y in re.findall(r"20\d{2}", text[desc : desc + 200])[:6]]
    if len(years) < 6:
        raise ValueError(f"EDB years header incomplete: {years}")

    result: dict = {"years": years}
    for key, label in LABELS.items():
        i = text.find(label)
        if i < 0:
            raise ValueError(f"label missing: {label}")
        usd = text.find("US $ Mn", i)
        if usd < 0:
            raise ValueError(f"US $ row missing after: {label}")
        values = [int(n.replace(",", "")) for n in NUM_RE.findall(text[usd : usd + 300])[:6]]
        if len(values) < 6:
            raise ValueError(f"incomplete series for {label}: {values}")
        result[key] = values
    return result
