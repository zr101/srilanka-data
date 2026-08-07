"""CBSL activity indicators: IIP, PMI and the Business Sentiment Index.

Three different layouts, all transposed relative to the price tables — periods
run across the columns rather than down a period column.
"""

from pipeline import xlsx


def parse_iip(wb) -> dict:
    """Index of Industrial Production: ISIC divisions down, year blocks across.

    ⚠ The year header is not trustworthy. In the 2026-07-27 vintage the final
    two blocks are BOTH labelled "2025" — "2025 (a)" (Revised, 12 months) and
    "2025 (b)" (Provisional, 5 months) — where the second is really 2026: it is
    the eleventh block after 2016, its five months match the Jan–May 2026 the
    Economic Data Library reports, and its values are ~4% above the same months
    of 2025 rather than a revision of them. Years are therefore derived from
    block position and the label is kept only as a cross-check, with any
    disagreement reported in `notes` instead of silently resolved either way.
    """
    ws = xlsx.sheet(wb, "1.04") or wb[wb.sheetnames[0]]
    month_row = xlsx.find_row(ws, "isic", column=1)
    if month_row is None:
        raise ValueError("IIP: no 'ISIC' header row")
    year_row = month_row - 1

    blocks = [
        (cell.column, xlsx.norm(cell.value))
        for cell in ws[year_row]
        if cell.value is not None and cell.column > 2
    ]
    blocks.sort()
    if not blocks:
        raise ValueError("IIP: no year blocks")

    base_year = int(xlsx.num(blocks[0][1].split()[0]) or 0)
    notes: list[str] = []
    columns: dict[str, int] = {}  # period -> column
    for offset, (start_col, label) in enumerate(blocks):
        year = base_year + offset
        labelled = label.split()[0]
        if labelled.isdigit() and int(labelled) != year:
            notes.append(
                f"year header {label!r} at block {offset} reads {labelled}, "
                f"using {year} from block position"
            )
        end_col = blocks[offset + 1][0] if offset + 1 < len(blocks) else ws.max_column + 1
        for col in range(start_col, end_col):
            month = xlsx.month_of(ws.cell(month_row, col).value)
            if month:
                columns[f"{year}-{month:02d}"] = col

    # Search below the header: the sheet title repeats this same label in row 1.
    total_row = xlsx.find_row(
        ws, "indexofindustrialproduction", column=1, limit=ws.max_row, start=month_row + 1
    )
    if total_row is None:
        raise ValueError("IIP: no 'Index of Industrial Production' total row")
    total: dict[str, float | None] = {}
    industries: list[dict] = []
    for row in range(month_row + 1, ws.max_row + 1):
        code, name = xlsx.norm(ws.cell(row, 1).value), xlsx.norm(ws.cell(row, 2).value)
        if row == total_row:
            total = {t: xlsx.num(ws.cell(row, c).value) for t, c in columns.items()}
            continue
        if not code or not name:
            continue
        points = {t: xlsx.num(ws.cell(row, c).value) for t, c in columns.items()}
        latest = xlsx.series(points)
        if latest:
            industries.append({"isic": code, "name": name, "latest": latest[-1]})

    return {
        "total": xlsx.series(total),
        "by_industry": industries,
        "notes": notes,
    }


def parse_pmi(wb) -> dict:
    """Purchasing Managers' Index — one sheet per sector, dates along row 2."""
    out: dict[str, dict] = {}
    for slug, needle in (("manufacturing", "pmi - m"), ("services", "pmi - s"), ("construction", "pmi - c")):
        ws = xlsx.sheet(wb, needle)
        if ws is None:
            continue
        header = next(
            (r for r in range(1, 6) if any(
                hasattr(ws.cell(r, c).value, "year") for c in range(2, ws.max_column + 1)
            )),
            None,
        )
        if header is None:
            continue
        columns = {}
        for col in range(2, ws.max_column + 1):
            stamp = ws.cell(header, col).value
            if hasattr(stamp, "year"):
                columns[f"{stamp.year}-{stamp.month:02d}"] = col
        sector: dict[str, list] = {}
        for row in range(header + 1, ws.max_row + 1):
            label = xlsx.norm(ws.cell(row, 1).value)
            if not label:
                continue
            name = xlsx.key(label).replace("index", "") or "pmi"
            points = {t: xlsx.num(ws.cell(row, c).value) for t, c in columns.items()}
            values = xlsx.series(points)
            if values:
                sector[name] = values
        if sector:
            out[slug] = sector
    if not out:
        raise ValueError("PMI: no sector sheets parsed")
    return out


def parse_bsi(wb) -> dict:
    """Business Sentiment Index — year row over quarter row, indicators down.

    Only rows carrying their own label are read. Each labelled row is followed
    by an unlabelled row of negative-signed figures whose meaning the workbook
    never states; those are left alone rather than guessed at.
    """
    ws = xlsx.sheet(wb, "bsi") or wb[wb.sheetnames[0]]
    quarter_row = xlsx.find_row(ws, "q1", column=2) or xlsx.find_row(ws, "q2", column=2)
    if quarter_row is None:
        raise ValueError("BSI: no quarter header row")
    years = xlsx.forward_fill(ws, quarter_row - 1)

    columns: dict[str, int] = {}
    for col in range(2, ws.max_column + 1):
        quarter = xlsx.norm(ws.cell(quarter_row, col).value).upper()
        year = xlsx.norm(years[col - 1]).split()[0] if years[col - 1] else ""
        if quarter.startswith("Q") and year.isdigit():
            columns[f"{year}-{quarter}"] = col

    out: dict[str, list] = {}
    for row in range(quarter_row + 1, ws.max_row + 1):
        label = xlsx.norm(ws.cell(row, 1).value)
        if not label:
            continue  # the unlabelled companion row
        points = {t: xlsx.num(ws.cell(row, c).value) for t, c in columns.items()}
        values = xlsx.series(points)
        if values:
            out[xlsx.key(label)] = values
    if not out:
        raise ValueError("BSI: no indicator rows")
    return out
