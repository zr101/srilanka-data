"""NMRA valid-registrations XLS (legacy BIFF8) → cleaned rows + summary.

Audit fixes (2026-08-08): REG.DATE cells are xldate floats and must be
converted via the workbook datemode (they previously serialized as "44477.0");
`***`-style placeholders map to empty (previously mangled by an rstrip that
could also truncate legitimate values).
"""

import re

import xlrd

PLACEHOLDER_RE = re.compile(r"^(\*+|N/?A|-+)$", re.I)


def clean_cell(value) -> str:
    text = re.sub(r"\s+", " ", str(value)).strip()
    if PLACEHOLDER_RE.match(text):
        return ""
    return text


def parse_xls(path: str) -> tuple[list[str], list[list[str]]]:
    book = xlrd.open_workbook(path)
    sheet = book.sheet_by_index(0)
    header = [clean_cell(c.value) for c in sheet.row(0)]
    date_cols = [i for i, h in enumerate(header) if "date" in h.lower()]
    rows = []
    for r in range(1, sheet.nrows):
        cells = sheet.row(r)
        row = []
        for i, c in enumerate(cells):
            if i in date_cols and c.ctype == xlrd.XL_CELL_DATE:
                dt = xlrd.xldate.xldate_as_datetime(c.value, book.datemode)
                row.append(dt.date().isoformat())
            else:
                row.append(clean_cell(c.value))
        if any(row):
            rows.append(row)
    return header, rows


def summarize(header: list[str], rows: list[list[str]]) -> dict:
    def col(name: str) -> int | None:
        for i, h in enumerate(header):
            if name.lower() in h.lower():
                return i
        return None

    country_idx = col("country")
    type_idx = col("regi. type") or col("type")
    date_idx = col("reg.date") or col("date")

    countries: dict[str, int] = {}
    types: dict[str, int] = {}
    newest_date = None
    for row in rows:
        if country_idx is not None:
            c = row[country_idx] or "UNKNOWN"
            countries[c] = countries.get(c, 0) + 1
        if type_idx is not None and row[type_idx]:
            types[row[type_idx]] = types.get(row[type_idx], 0) + 1
        if date_idx is not None and re.match(r"^\d{4}-\d{2}-\d{2}$", row[date_idx] or ""):
            if newest_date is None or row[date_idx] > newest_date:
                newest_date = row[date_idx]

    top = sorted(countries.items(), key=lambda kv: -kv[1])[:10]
    return {
        "total_registrations": len(rows),
        "top_countries": [{"country": c, "count": n} for c, n in top],
        "by_type": types,
        "newest_reg_date": newest_date,
    }
