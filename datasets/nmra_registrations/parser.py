"""NMRA valid-registrations XLS (legacy BIFF8) → cleaned rows + summary."""

import xlrd


def clean_cell(value) -> str:
    text = str(value).strip()
    # upstream data carries junk trailing characters like "BANGLADESH!" / "SRI LANKA+"
    return text.rstrip("!+*#~ ").strip()


def parse_xls(path: str) -> tuple[list[str], list[list[str]]]:
    book = xlrd.open_workbook(path)
    sheet = book.sheet_by_index(0)
    header = [clean_cell(c.value) for c in sheet.row(0)]
    rows = []
    for i in range(1, sheet.nrows):
        row = [clean_cell(c.value) for c in sheet.row(i)]
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
    countries: dict[str, int] = {}
    if country_idx is not None:
        for row in rows:
            c = row[country_idx] or "UNKNOWN"
            countries[c] = countries.get(c, 0) + 1
    top = sorted(countries.items(), key=lambda kv: -kv[1])[:10]
    return {
        "total_registrations": len(rows),
        "top_countries": [{"country": c, "count": n} for c, n in top],
    }
