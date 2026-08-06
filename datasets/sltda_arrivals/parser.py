"""SLTDA arrivals report: line-oriented regex over the PDF text
(tables are line-adjacent: '1 India 338,230', 'January 238,924 252,761 ...')."""

import io
import re

import pdfplumber

MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
PCT = r"\(?-?[\d.]+\)?"  # negative changes print as "(19.7)"
MONTH_ROW_RE = re.compile(
    rf"^({'|'.join(MONTHS)})\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+({PCT})\s+({PCT})"
)
MARKET_ROW_RE = re.compile(r"^(\d{1,2})\s+([A-Za-z][A-Za-z .&'()-]+?)\s+([\d,]+)\s*$")


def _int(text: str) -> int:
    return int(text.replace(",", ""))


def parse_pdf(payload: bytes) -> dict:
    lines: list[str] = []
    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        for page in pdf.pages:
            lines.extend((page.extract_text() or "").split("\n"))

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
                }
            )

    # rank/country/value rows appear in runs (monthly table, then YTD table);
    # the run with the larger total is the YTD table.
    runs: list[list[dict]] = []
    current: list[dict] = []
    for line in lines:
        m = MARKET_ROW_RE.match(line.strip())
        if m and (not current or int(m.group(1)) == len(current) + 1):
            current.append({"rank": int(m.group(1)), "country": m.group(2).strip(), "arrivals": _int(m.group(3))})
        else:
            if len(current) >= 5:
                runs.append(current)
            current = [] if not m else [
                {"rank": int(m.group(1)), "country": m.group(2).strip(), "arrivals": _int(m.group(3))}
            ]
    if len(current) >= 5:
        runs.append(current)
    top_markets_ytd = max(runs, key=lambda r: sum(x["arrivals"] for x in r)) if runs else []

    if not months and not top_markets_ytd:
        raise ValueError("SLTDA parse found neither monthly rows nor market tables")
    return {
        "months": months,
        "ytd_total": sum(m["arrivals_this_year"] for m in months) if months else None,
        "top_markets_ytd": top_markets_ytd[:20],
    }
