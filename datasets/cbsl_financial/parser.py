"""CBSL financial sector: banking soundness indicators.

One workbook, five sheets (capital adequacy, asset quality, earnings,
liquidity, funding structure), all sharing a year-over-quarter header with a
code column and an indicator label column.
"""

import re

from pipeline import xlsx


def _quarter_columns(ws, year_row: int, quarter_row: int) -> dict[str, int]:
    years = xlsx.forward_fill(ws, year_row)
    out: dict[str, int] = {}
    for col in range(2, ws.max_column + 1):
        quarter = xlsx.norm(ws.cell(quarter_row, col).value).upper()
        raw = xlsx.norm(years[col - 1]) if years[col - 1] else ""
        year = re.search(r"(19|20)\d{2}", raw)
        if re.fullmatch(r"Q[1-4]", quarter) and year:
            out.setdefault(f"{year.group(0)}-{quarter}", col)
    return out


def parse_soundness(wb) -> dict:
    """Every sheet of the soundness workbook, keyed by folded sheet name."""
    out: dict[str, list[dict]] = {}
    for name in wb.sheetnames:
        ws = wb[name]
        quarter_row = next(
            (
                r
                for r in range(1, 12)
                if sum(
                    bool(re.fullmatch(r"Q[1-4]", xlsx.norm(ws.cell(r, c).value).upper()))
                    for c in range(2, ws.max_column + 1)
                )
                >= 2
            ),
            None,
        )
        if quarter_row is None:
            continue
        columns = _quarter_columns(ws, quarter_row - 1, quarter_row)
        if not columns:
            continue

        indicators = []
        for row in range(quarter_row + 1, ws.max_row + 1):
            code = xlsx.norm(ws.cell(row, 1).value)
            label = xlsx.norm(ws.cell(row, 2).value)
            if not label:
                continue
            points = xlsx.series({t: xlsx.num(ws.cell(row, c).value) for t, c in columns.items()})
            if points:
                indicators.append({"code": code or None, "label": label, "points": points})
        if indicators:
            out[xlsx.key(name)] = indicators
    if not out:
        raise ValueError("soundness: no sheets parsed")
    return out


def find_indicator(soundness: dict, sheet: str, *needles: str) -> list[dict]:
    """Latest series for one indicator, matched on its label."""
    wanted = [xlsx.key(n) for n in needles]
    for indicator in soundness.get(sheet, []):
        if all(w in xlsx.key(indicator["label"]) for w in wanted):
            return indicator["points"]
    return []


def parse_finance_companies(wb) -> dict:
    """Licensed finance companies (LFC) sector — quarter-end dates across the
    top, line items down. A different shape from the banking workbooks, which
    put years over quarters."""
    out: dict[str, list[dict]] = {}
    for name in wb.sheetnames:
        ws = wb[name]
        header = next(
            (
                r
                for r in range(1, 8)
                if sum(hasattr(ws.cell(r, c).value, "year") for c in range(2, ws.max_column + 1)) >= 2
            ),
            None,
        )
        if header is None:
            continue
        columns = {}
        for col in range(2, ws.max_column + 1):
            stamp = ws.cell(header, col).value
            if hasattr(stamp, "year"):
                columns[f"{stamp.year}-Q{(stamp.month - 1) // 3 + 1}"] = col
        if not columns:
            continue
        # Labels sit immediately left of the first dated column; these sheets
        # carry a blank column A, so column 1 is not a safe assumption.
        label_col = min(columns.values()) - 1
        rows = []
        for row in range(header + 1, ws.max_row + 1):
            label = xlsx.norm(ws.cell(row, label_col).value)
            if not label:
                continue
            points = xlsx.series({t: xlsx.num(ws.cell(row, c).value) for t, c in columns.items()})
            if points:
                rows.append({"label": label, "points": points})
        if rows:
            out[xlsx.key(name)] = rows
    if not out:
        raise ValueError("finance companies: no sheets parsed")
    return out


def parse_outlets(wb) -> dict:
    """Table 4.0 Distribution of Banking Outlets — districts down, years across.

    Annual and district-keyed, unlike the year-over-quarter layout the rest of
    the financial-sector family shares.
    """
    out: dict[str, list[dict]] = {}
    for name in wb.sheetnames:
        ws = wb[name]
        year_row = next(
            (
                r
                for r in range(1, 12)
                if sum(
                    bool(re.fullmatch(r"(19|20)\d{2}", xlsx.norm(ws.cell(r, c).value)))
                    for c in range(1, ws.max_column + 1)
                )
                >= 3
            ),
            None,
        )
        if year_row is None:
            continue
        columns = {
            xlsx.norm(ws.cell(year_row, c).value): c
            for c in range(1, ws.max_column + 1)
            if re.fullmatch(r"(19|20)\d{2}", xlsx.norm(ws.cell(year_row, c).value))
        }
        label_col = max(
            range(1, min(columns.values())),
            key=lambda c: sum(
                1
                for r in range(year_row + 1, min(ws.max_row, year_row + 40) + 1)
                if xlsx.norm(ws.cell(r, c).value) and not xlsx.num(ws.cell(r, c).value)
            ),
        )
        districts = []
        for row in range(year_row + 1, ws.max_row + 1):
            label = xlsx.norm(ws.cell(row, label_col).value)
            if not label or xlsx.num(label) is not None:
                continue
            points = xlsx.series({t: xlsx.num(ws.cell(row, c).value) for t, c in columns.items()})
            if points:
                districts.append({"district": label.title(), "points": points})
        if districts:
            out[xlsx.key(name)] = districts
    if not out:
        raise ValueError("outlets: no sheets parsed")
    return out
