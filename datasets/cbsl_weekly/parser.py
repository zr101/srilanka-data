"""CBSL Weekly Economic Indicators: the tables are z-scrambled but the
first-page prose highlights carry the headline numbers in stable phrasing."""

import io
import re

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

    if "reserves_usd_mn" not in out and "exports_usd_mn" not in out:
        raise ValueError("WEI prose highlights not found — layout may have changed")
    return out
