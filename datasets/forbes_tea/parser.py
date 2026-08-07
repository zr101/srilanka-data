"""Forbes & Walker 'Weekly Tea Auction Quantities & Averages' — one clean
line-oriented table covering the whole year (qty '000 kg + avg Rs by elevation).
Known upstream defect: a 2026 row misprints the year as 2027 — repaired when the
month sequence proves it in-year (audit 2026-08-08)."""

import io
import re
from datetime import datetime

import pdfplumber

ROW_RE = re.compile(
    r"^(\d{2})-([A-Z]{3,9})-(\d{4})\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+"
    r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*$"
)
MONTHS = {m.upper(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)}


def _int(t: str) -> int:
    return int(t.replace(",", ""))


def parse_pdf(payload: bytes, expected_year: int) -> dict:
    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    sales = []
    repaired = 0
    for line in text.split("\n"):
        m = ROW_RE.match(line.strip())
        if not m:
            continue
        day, mon_name, year = int(m.group(1)), m.group(2), int(m.group(3))
        month = next((n for name, n in MONTHS.items() if name.startswith(mon_name)), None)
        if month is None:
            continue
        if year != expected_year:
            year = expected_year  # upstream typo guard (observed "01-JUL-2027")
            repaired += 1
        date = datetime(year, month, day).date().isoformat()
        qty = {"high": _int(m.group(4)), "medium": _int(m.group(5)), "low": _int(m.group(6)), "total": _int(m.group(7))}
        avg = {"high": float(m.group(8)), "medium": float(m.group(9)), "low": float(m.group(10)), "total": float(m.group(11))}
        if qty["high"] + qty["medium"] + qty["low"] != qty["total"]:
            raise ValueError(f"{date}: qty High+Med+Low != Total")
        if not min(avg["high"], avg["medium"], avg["low"]) <= avg["total"] <= max(avg["high"], avg["medium"], avg["low"]):
            raise ValueError(f"{date}: total avg outside elevation range")
        sales.append({"sale_date": date, "qty_000kg": qty, "avg_rs": avg})
    if len(sales) < 4:
        raise ValueError(f"only {len(sales)} sale rows parsed")
    sales.sort(key=lambda s: s["sale_date"])
    return {"year": expected_year, "sales": sales, "latest": sales[-1], "repaired_year_rows": repaired}
