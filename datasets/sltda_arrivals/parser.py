"""SLTDA arrivals report: line-oriented regex over the PDF text
(tables are line-adjacent: '1 India 338,230', 'January 238,924 252,761 ...')."""

import io
import re
import sys
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from pipeline.derotate import connected_labels  # noqa: E402

DAILY_DATE_RE = re.compile(r"^(\d{2})-([A-Za-z]{3})-(\d{2})$")
DAILY_VAL_RE = re.compile(r"^[\d,]{3,7}$")


def parse_daily_series(page) -> list[dict]:
    """Daily arrivals from the rotated chart labels: pair each value label to
    the nearest date label by column x (kills y-axis ticks automatically)."""
    labels = connected_labels(page.chars)
    dates = [l for l in labels if DAILY_DATE_RE.match(l["text"])]
    values = [l for l in labels if DAILY_VAL_RE.match(l["text"])]
    series = []
    for d in dates:
        candidates = [v for v in values if abs(v["x"] - d["x"]) <= 10]
        if not candidates:
            continue
        v = min(candidates, key=lambda v: abs(v["x"] - d["x"]))
        m = DAILY_DATE_RE.match(d["text"])
        series.append(
            {
                "date": f"20{m.group(3)}-{_month_num(m.group(2)):02d}-{int(m.group(1)):02d}",
                "arrivals": int(v["text"].replace(",", "")),
            }
        )
    series.sort(key=lambda s: s["date"])
    return series


def _month_num(abbr: str) -> int:
    return ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].index(abbr.lower()) + 1

MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
PCT = r"\(?-?[\d.]+\)?"  # negative changes print as "(19.7)"
MONTH_ROW_RE = re.compile(
    rf"^({'|'.join(MONTHS)})\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+({PCT})\s+({PCT})"
)
# p7 YTD rows end in the arrivals number; p6 monthly rows carry a trailing share %
MARKET_ROW_RE = re.compile(r"^(\d{1,2})\s+([A-Za-z][A-Za-z .&'()-]+?)\s+([\d,]+)(?:\s+([\d.]+)%)?\s*$")


def _int(text: str) -> int:
    return int(text.replace(",", ""))


def _pct(text: str | None) -> float | None:
    if not text:
        return None
    return -float(text[1:-1]) if text.startswith("(") else float(text.strip("()"))


def parse_pdf(payload: bytes) -> dict:
    pages: list[list[str]] = []
    daily: list[dict] = []
    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        for page in pdf.pages:
            pages.append((page.extract_text() or "").split("\n"))
            if not daily:
                candidate = parse_daily_series(page)
                if len(candidate) >= 25:  # the daily chart page
                    daily = candidate
    lines = [line for page in pages for line in page]

    months = []
    for line in lines:
        m = MONTH_ROW_RE.match(line.strip())
        if m:
            months.append(
                {
                    "month": m.group(1),
                    "arrivals_prior_ref": _int(m.group(2)),
                    "arrivals_last_year": _int(m.group(3)),
                    "arrivals_this_year": _int(m.group(4)),
                    "pct_change_yoy": _pct(m.group(5)),
                }
            )

    # markets: collect all rank rows PER PAGE (decorative infographic lines
    # interleave with the table, so consecutive-run collection under-collects —
    # audit fix); a page whose ranks form a dense 1..N (N≥5) holds a table.
    def market_table(page_lines: list[str]) -> tuple[list[dict], int | None]:
        rows: dict[int, dict] = {}
        total = None
        for line in page_lines:
            m = MARKET_ROW_RE.match(line.strip())
            if m:
                rank = int(m.group(1))
                rows[rank] = {
                    "rank": rank,
                    "country": m.group(2).strip(),
                    "arrivals": _int(m.group(3)),
                    **({"share_pct": float(m.group(4))} if m.group(4) else {}),
                }
            tm = re.match(r"^(?:TOTAL|Total)\s+([\d,]+)\s*$", line.strip())
            if tm:
                total = _int(tm.group(1))
        n = len(rows)
        if n >= 5 and sorted(rows) == list(range(1, n + 1)):
            return [rows[r] for r in sorted(rows)], total
        return [], total

    top_markets_month: list[dict] = []
    top_markets_ytd: list[dict] = []
    headline = None
    ytd_table_total = None
    for page_lines in pages:
        table, total = market_table(page_lines)
        if not table:
            continue
        if any("share_pct" in row for row in table) and not top_markets_month:
            top_markets_month = table
            headline = total  # the share-table Total row IS the monthly headline
        elif not any("share_pct" in row for row in table):
            top_markets_ytd = table  # later page (YTD) wins
            ytd_table_total = total

    if not months and not top_markets_ytd:
        raise ValueError("SLTDA parse found neither monthly rows nor market tables")
    daily_sum = sum(x["arrivals"] for x in daily)
    return {
        "months": months,
        "ytd_total": sum(m["arrivals_this_year"] for m in months) if months else None,
        "month_headline": headline,
        "daily": daily,
        # exact-but-partial is acceptable; wrong numbers are not — a few chart
        # labels resist de-rotation, so completeness is declared, not assumed
        "daily_complete": bool(headline) and abs(daily_sum - (headline or 0)) <= 2,
        "daily_sum": daily_sum,
        "top_markets_month": top_markets_month[:10],
        "top_markets_ytd": top_markets_ytd[:20],
    }


def rebuild(payload: bytes, _existing: dict) -> dict:
    clean = parse_pdf(payload)
    if _existing.get("period"):
        clean["period"] = _existing["period"]
    return clean
