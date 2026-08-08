"""CBSL fiscal sector: government fiscal operations and outstanding debt.

Both are annual tables with a two-tier header, so columns are named
`<group>_<subheader>` and emitted wholesale rather than cherry-picked — the
column block has grown over time (new revenue lines appear between vintages)
and a fixed list would silently drop them.
"""

from pipeline import xlsx


def _grid(ws, group_row: int, first_data_row: int) -> dict:
    columns = xlsx.leaf_columns(ws, group_row, group_row + 1, start_col=2)
    year_col = next((c for slug, c in columns.items() if slug.startswith("year")), 2)
    out: dict[str, dict[str, float | None]] = {}
    for row, period in xlsx.periods_down(ws, first_data_row, "annual", year_col):
        for slug, col in columns.items():
            if col == year_col:
                continue
            out.setdefault(slug, {})[period] = xlsx.num(ws.cell(row, col).value)
    return {slug: xlsx.series(points) for slug, points in out.items() if xlsx.series(points)}


def parse_operations(wb) -> dict:
    """3.1 Summary of Government Fiscal Operations (Rs. million, annual)."""
    ws = xlsx.sheet(wb, "3.1") or wb[wb.sheetnames[0]]
    header = xlsx.find_row(ws, "year", column=2)
    if header is None:
        raise ValueError("fiscal operations: no 'Year' header")
    return _grid(ws, header, header + 2)


def parse_revenue(wb) -> dict:
    """3.02 Economic Classification of Government Revenue (Rs. million, annual)."""
    ws = xlsx.sheet(wb, "3.02") or wb[wb.sheetnames[0]]
    header = xlsx.find_row(ws, "year", column=2)
    if header is None:
        raise ValueError("revenue: no 'Year' header")
    return _grid(ws, header, header + 2)


def parse_expenditure(wb) -> dict:
    """3.04 Economic Classification of Government Expenditure (Rs. million, annual)."""
    ws = xlsx.sheet(wb, "3.04") or wb[wb.sheetnames[0]]
    header = xlsx.find_row(ws, "year", column=2)
    if header is None:
        raise ValueError("expenditure: no 'Year' header")
    return _grid(ws, header, header + 2)


def parse_debt(wb) -> dict:
    """3.5 Central Government Outstanding Debt (Rs. million, annual)."""
    ws = xlsx.sheet(wb, "3.05") or wb[wb.sheetnames[0]]
    header = xlsx.find_row(ws, "year", column=2)
    if header is None:
        raise ValueError("debt: no 'Year' header")
    return _grid(ws, header, header + 2)
