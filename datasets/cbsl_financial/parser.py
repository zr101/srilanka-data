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
