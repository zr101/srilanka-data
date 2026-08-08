"""CBSL monetary sector: interest rates, reserve money and the monetary survey.

Each workbook encodes its period differently — a Year column beside a Month
column, a single "2003 Jan" column that then goes bare, and real date cells —
which is why pipeline.xlsx.periods_down carries four modes.
"""

import re

from pipeline import xlsx

MAX_MONTHS = 120  # ten years; full history stays in each stored doc


def _down(ws, group_row: int, sub_row: int, first_row: int, mode: str, year_col: int, month_col=None, end_row=None) -> dict:
    columns = xlsx.leaf_columns(ws, group_row, sub_row, start_col=year_col + 1)
    out: dict[str, dict[str, float | None]] = {}
    for row, period in xlsx.periods_down(ws, first_row, mode, year_col, month_col, end_row):
        for slug, col in columns.items():
            if col in (year_col, month_col):
                continue
            out.setdefault(slug, {})[period] = xlsx.num(ws.cell(row, col).value)
    return {
        slug: xlsx.series(points, keep=MAX_MONTHS)
        for slug, points in out.items()
        if xlsx.series(points)
    }


def parse_interest_rates(wb) -> dict:
    """4.04 Interest Rates — Monthly. Year and month sit in separate columns."""
    ws = xlsx.sheet(wb, "4.04") or wb[wb.sheetnames[0]]
    header = xlsx.find_row(ws, "endofperiod", column=2)
    if header is None:
        raise ValueError("interest rates: no 'End of Period' header")
    # A row of column ordinals (-1, -2, …) sits between the header and the data.
    first = header + 1
    while first <= ws.max_row and not any(
        xlsx.month_of(ws.cell(first, c).value) for c in (2, 3)
    ):
        first += 1
    return _down(ws, header, header, first, "split", year_col=2, month_col=3)


def parse_reserve_money(wb) -> dict:
    """4.11 Reserve Money, Money Multiplier and Velocity — Monthly."""
    ws = xlsx.sheet(wb, "4.11") or wb[wb.sheetnames[0]]
    header = xlsx.find_row(ws, "endoftheyear", column=2) or xlsx.find_row(ws, "endof", column=2)
    if header is None:
        raise ValueError("reserve money: no period header")
    return _down(ws, header, header + 1, header + 2, "inline", year_col=2)


def parse_monetary_survey(wb) -> dict:
    """4.02 Monetary Survey — Monthly, with real date cells in the period column."""
    ws = xlsx.sheet(wb, "4.02")
    if ws is None:
        raise ValueError("monetary survey: no 4.02 sheet")
    header = xlsx.find_row(ws, "reservemoney", column=3) or xlsx.find_row(ws, "monetaryaggregates", column=3)
    if header is None:
        raise ValueError("monetary survey: no aggregates header")
    first = next(
        (r for r in range(header, ws.max_row + 1) if hasattr(ws.cell(r, 2).value, "year")), None
    )
    if first is None:
        raise ValueError("monetary survey: no dated rows")
    return _down(ws, header, header + 1, first, "datetime", year_col=2)


def parse_sectoral_credit(wb) -> dict:
    """4.02 'Sectoral Credit' — transposed: months across, sectors down."""
    ws = xlsx.sheet(wb, "sectoral credit")
    if ws is None:
        return {}
    period_row = next(
        (
            r
            for r in range(1, min(ws.max_row, 20) + 1)
            if sum(hasattr(ws.cell(r, c).value, "year") for c in range(2, ws.max_column + 1)) >= 3
        ),
        None,
    )
    if period_row is None:
        return {}
    columns = {}
    for col in range(2, ws.max_column + 1):
        stamp = ws.cell(period_row, col).value
        if hasattr(stamp, "year"):
            columns[f"{stamp.year}-{stamp.month:02d}"] = col

    sectors = []
    for row in range(period_row + 1, ws.max_row + 1):
        code, name = xlsx.norm(ws.cell(row, 1).value), xlsx.norm(ws.cell(row, 2).value)
        if not code or not name:
            continue  # "of which…" continuation rows carry no code
        points = xlsx.series(
            {t: xlsx.num(ws.cell(row, c).value) for t, c in columns.items()}, keep=MAX_MONTHS
        )
        if points:
            sectors.append({"code": code, "name": name, "points": points})
    return {"sectors": sectors}


def _blocks(ws) -> list[tuple[int, int, str]]:
    """(header_row, end_row, banner) for each stacked table on the sheet.

    4.06 and 4.08 each hold an ASSETS table followed by a LIABILITIES table,
    both re-listing every period. Parsing the sheet as one grid merged them and
    let the liabilities rows overwrite the assets rows for the same month.
    """
    headers = [
        r
        for r in range(1, ws.max_row + 1)
        if "endofperiod" in xlsx.key(ws.cell(r, 2).value)
    ]
    out = []
    for i, header in enumerate(headers):
        end = headers[i + 1] - 1 if i + 1 < len(headers) else ws.max_row
        banner = "".join(
            xlsx.norm(ws.cell(header, c).value)
            for c in range(3, min(ws.max_column, 30) + 1)
        ).replace(" ", "")
        slug = "liabilities" if "LIABILIT" in banner.upper() else "assets"
        out.append((header, end, slug))
    return out


def _auto_down(ws) -> dict:
    """Parse a balance-sheet sheet without assuming header offsets.

    4.06 stacks three header tiers (a letter-spaced ASSETS banner, a group row,
    then leaf labels) while 4.08 uses one tier and dates its rows with real
    date cells rather than "2003 Jan" text. Both are found by locating the
    period column, then the first row whose period cell actually parses, and
    treating the row above it that carries the most labels as the leaf header.
    """
    period_col = 2
    result: dict[str, list] = {}
    for header, block_end, slug in _blocks(ws):
        result[slug] = (header, block_end)
    if not result:
        raise ValueError(f"{ws.title}: no 'End of Period' header")

    def period_at(row: int) -> str | None:
        value = ws.cell(row, period_col).value
        if hasattr(value, "year"):
            return "datetime"
        text = xlsx.norm(value)
        return "inline" if re.match(r"(19|20)\d{2}", text) else None

    # The leaf header is the labelled row nearest the data; rows of column
    # ordinals (-1, -2, ...) sit between it and the data and must not win.
    def label_count(row: int) -> int:
        return sum(
            1
            for c in range(period_col + 1, ws.max_column + 1)
            if xlsx.key(ws.cell(row, c).value)
            and not re.fullmatch(r"-?\d+", xlsx.norm(ws.cell(row, c).value))
        )

    out: dict[str, dict] = {}
    for slug, (header, block_end) in result.items():
        first = next(
            (r for r in range(header + 1, min(block_end, header + 20) + 1) if period_at(r)), None
        )
        if first is None:
            continue
        mode = period_at(first)
        leaf = max(range(header, first), key=label_count)
        if label_count(leaf) < 3:
            continue
        for name, series in _down(
            ws, leaf - 1, leaf, first, mode, year_col=period_col, end_row=block_end
        ).items():
            out[f"{slug}_{name}"] = series
    if not out:
        raise ValueError(f"{ws.title}: no block parsed")
    return out




def parse_cbsl_balance_sheet(wb) -> dict:
    """4.06 Assets and Liabilities of the Central Bank — Monthly."""
    return _auto_down(xlsx.sheet(wb, "4.06") or wb[wb.sheetnames[0]])


def parse_bank_balance_sheet(wb) -> dict:
    """4.08 Assets and Liabilities of Commercial Banks — Monthly.

    Two sheets: domestic banking units and offshore banking units.
    """
    out = {}
    for slug, needle in (("dbu", "dbu"), ("obu", "obu")):
        ws = xlsx.sheet(wb, needle)
        if ws is None:
            continue
        try:
            out[slug] = _auto_down(ws)
        except ValueError as err:
            print(f"  bank balance sheet {slug}: {err}")
    if not out:
        raise ValueError("bank balance sheet: no DBU/OBU sheets")
    return out
