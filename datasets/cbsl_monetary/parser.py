"""CBSL monetary sector: interest rates, reserve money and the monetary survey.

Each workbook encodes its period differently — a Year column beside a Month
column, a single "2003 Jan" column that then goes bare, and real date cells —
which is why pipeline.xlsx.periods_down carries four modes.
"""

from pipeline import xlsx

MAX_MONTHS = 120  # ten years; full history stays in each stored doc


def _down(ws, group_row: int, sub_row: int, first_row: int, mode: str, year_col: int, month_col=None) -> dict:
    columns = xlsx.leaf_columns(ws, group_row, sub_row, start_col=year_col + 1)
    out: dict[str, dict[str, float | None]] = {}
    for row, period in xlsx.periods_down(ws, first_row, mode, year_col, month_col):
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
