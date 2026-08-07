"""CBSL prices: CCPI/NCPI index levels and wage rate indices.

The two CPI workbooks share one layout — a two-tier header (measure group over
`<INDEX>` / `<INDEX> Core`) above a 'YYYY Month' period column. Everything is
located by header text because the column block changes width between vintages
(the annual-average group was added after the 2021 rebase).

Widens what the monitor already has: the inflation widget behind
lib/sources/cbslInflation.ts publishes Y-o-Y only, while these carry the index
levels, monthly change and annual-average change too.
"""

from pipeline import xlsx

# Measure group header → output key. Matched folded, as substrings, because the
# workbook writes "Year-on-Year % Change" and "Y-o-Y % Change" in different vintages.
MEASURES = [
    ("index", "index"),
    ("monthlychange", "monthly_pct"),
    ("yearonyearchange", "yoy_pct"),
    ("yoychange", "yoy_pct"),
    ("annualaveragechange", "annual_avg_pct"),
]


def _measure_key(header: str) -> str | None:
    folded = xlsx.key(header)
    for needle, out in MEASURES:
        if needle in folded:
            return out
    return None


def parse_cpi(wb, index_name: str) -> dict:
    """Parse CCPI_and_CCPI_CORE / NCPI_and_NCPI_CORE into per-measure series.

    Returns {"index": [...], "index_core": [...], "monthly_pct": [...], ...}
    with each series a sorted list of {"t": "YYYY-MM", "v": float}.
    """
    ws = xlsx.sheet(wb, index_name.lower())
    if ws is None:
        raise ValueError(f"no {index_name} sheet in {wb.sheetnames}")

    header_row = xlsx.find_row(ws, "period", column=2) or xlsx.find_row(ws, "period", column=1)
    if header_row is None:
        raise ValueError(f"{index_name}: no 'Period' header row")
    period_col = next(
        col
        for col in range(1, ws.max_column + 1)
        if xlsx.key(ws.cell(header_row, col).value) == "period"
    )

    # Measure groups are merged across their two sub-columns, so forward-fill
    # the group row and read the variant (base vs Core) from the row below.
    groups = xlsx.forward_fill(ws, header_row)
    columns: dict[tuple[str, str], int] = {}
    for col in range(period_col + 1, ws.max_column + 1):
        measure = _measure_key(groups[col - 1] or "")
        variant = xlsx.key(ws.cell(header_row + 1, col).value)
        if not measure or not variant:
            continue
        suffix = "_core" if "core" in variant else ""
        columns.setdefault((measure, suffix), col)

    if not columns:
        raise ValueError(f"{index_name}: no measure columns under {groups[:12]}")

    out: dict[str, dict[str, float | None]] = {}
    for row in range(header_row + 2, ws.max_row + 1):
        period = xlsx.period_of(ws.cell(row, period_col).value)
        if not period:
            continue  # blank rows, footnotes and the source line
        for (measure, suffix), col in columns.items():
            out.setdefault(measure + suffix, {})[period] = xlsx.num(ws.cell(row, col).value)

    return {name: xlsx.series(points) for name, points in out.items()}


def parse_wages(wb) -> dict:
    """Wage Rate Indices: Year/Month rows against Nominal+Real per sector.

    The Year cell is merged down its twelve months, so it is forward-filled
    from the last seen value rather than read per row.
    """
    ws = xlsx.sheet(wb, "wage") or wb[wb.sheetnames[0]]
    header_row = xlsx.find_row(ws, "year", column=1)
    if header_row is None:
        raise ValueError("wages: no 'Year' header row")

    sectors = xlsx.forward_fill(ws, header_row)
    columns: dict[str, int] = {}
    for col in range(3, ws.max_column + 1):
        sector, variant = sectors[col - 1], xlsx.key(ws.cell(header_row + 1, col).value)
        if not sector or variant not in ("nominal", "real"):
            continue
        slug = "public" if "public" in xlsx.key(sector) else "informal_private"
        columns.setdefault(f"{slug}_{variant}", col)

    out: dict[str, dict[str, float | None]] = {}
    year = None
    for row in range(header_row + 2, ws.max_row + 1):
        year = xlsx.norm(ws.cell(row, 1).value) or year
        month = xlsx.month_of(ws.cell(row, 2).value)
        if not year or not month or not year.isdigit():
            continue
        period = f"{year}-{month:02d}"
        for name, col in columns.items():
            out.setdefault(name, {})[period] = xlsx.num(ws.cell(row, col).value)

    return {name: xlsx.series(points) for name, points in out.items()}


def latest_of(series: list[dict]) -> dict | None:
    return series[-1] if series else None
