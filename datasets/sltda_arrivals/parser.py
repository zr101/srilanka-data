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
    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        for page in pdf.pages:
            pages.append((page.extract_text() or "").split("\n"))
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

    # markets: collect rank runs PER PAGE — monthly top-10 (with share %) and
    # YTD top-20 live on different pages; page order disambiguates (audit fix:
    # the old "larger total" heuristic silently dropped the monthly table).
    def market_runs(page_lines: list[str]) -> list[list[dict]]:
        runs: list[list[dict]] = []
        current: list[dict] = []
        for line in page_lines:
            m = MARKET_ROW_RE.match(line.strip())
            if m and (not current or int(m.group(1)) == len(current) + 1):
                current.append(
                    {
                        "rank": int(m.group(1)),
                        "country": m.group(2).strip(),
                        "arrivals": _int(m.group(3)),
                        **({"share_pct": float(m.group(4))} if m.group(4) else {}),
                    }
                )
            else:
                if len(current) >= 5:
                    runs.append(current)
                current = []
        if len(current) >= 5:
            runs.append(current)
        return runs

    top_markets_month: list[dict] = []
    top_markets_ytd: list[dict] = []
    for page_lines in pages:
        for run in market_runs(page_lines):
            if any("share_pct" in row for row in run) and not top_markets_month:
                top_markets_month = run
            elif not any("share_pct" in row for row in run):
                top_markets_ytd = run  # later page (YTD) wins

    # MTD headline: "Tourist arrivals 01st to 31st July 2026" followed by the figure
    headline = None
    joined = " ".join(lines)
    hm = re.search(r"[Tt]ourist [Aa]rrivals[^\d]{0,40}0?1(?:st)?\s*(?:to|–|-)\s*\d{1,2}\w{0,2}\s+\w+\s+\d{4}\D{0,20}([\d,]{4,})", joined)
    if hm:
        headline = _int(hm.group(1))

    if not months and not top_markets_ytd:
        raise ValueError("SLTDA parse found neither monthly rows nor market tables")
    return {
        "months": months,
        "ytd_total": sum(m["arrivals_this_year"] for m in months) if months else None,
        "month_headline": headline,
        "top_markets_month": top_markets_month[:10],
        "top_markets_ytd": top_markets_ytd[:20],
    }
