"""CBSL external sector: reserve template, balance of payments, monthly trade.

The three hardest layouts in the statistical-table library:
  * the Reserve Data Template is a point-in-time snapshot whose sheet is
    renamed every month ("RDT (June 2026)"), so the as-of date is read from
    the sheet name rather than any cell;
  * the BOP puts each quarter over a Credit/Debit/Net triple and expresses the
    line-item hierarchy as *column depth* rather than indentation;
  * the trade books carry the reporting years in their sheet names
    ("2.02 In USD 2007-2026"), which roll over every January.

History is capped per table — these books hold 20 years of monthly detail and
the whole family is republished into one latest.json the dashboard fetches.
"""

from pipeline import xlsx

TRADE_MONTHS = 72  # six years of monthly detail
BOP_QUARTERS = 24


def parse_reserves(wb) -> dict:
    """Reserve Data Template — Table I official reserve assets, USD Mn."""
    ws = next((wb[n] for n in wb.sheetnames if xlsx.key(n).startswith("rdt")), wb[wb.sheetnames[0]])
    as_of = xlsx.norm(ws.title)
    value_col = None
    header = xlsx.find_row(ws, "usdmn", column=3) or xlsx.find_row(ws, "usdmn", column=2)
    for col in range(2, min(ws.max_column, 8) + 1):
        if any(xlsx.key(ws.cell(r, col).value) == "usdmn" for r in range(1, 12)):
            value_col = col
            break
    if value_col is None:
        raise ValueError(f"reserves: no 'USD Mn' column in {as_of}")

    items = []
    for row in range((header or 1) + 1, ws.max_row + 1):
        label = xlsx.norm(ws.cell(row, 1).value)
        value = xlsx.num(ws.cell(row, value_col).value)
        if not label or value is None:
            continue
        items.append({"label": label, "usd_mn": value})
        if xlsx.key(label).startswith("botherforeigncurrency"):
            break  # Table I ends here; Tables II+ are predetermined drains
    if not items:
        raise ValueError(f"reserves: no rows parsed from {as_of}")

    def find(*needles: str) -> float | None:
        wanted = [xlsx.key(n) for n in needles]
        return next(
            (i["usd_mn"] for i in items if all(w in xlsx.key(i["label"]) for w in wanted)), None
        )

    return {
        "as_of": as_of,
        "items": items,
        "official_reserve_assets_usd_mn": find("officialreserveassets"),
        "foreign_currency_reserves_usd_mn": find("foreigncurrencyreserves"),
        "gold_usd_mn": find("gold"),
        "sdr_usd_mn": find("sdrs"),
        "imf_position_usd_mn": find("imfreserveposition"),
    }


def parse_bop(wb) -> dict:
    """BOP (BPM6) quarterly — Credit/Debit/Net under each quarter."""
    ws = xlsx.sheet(wb, "current ac")
    if ws is None:
        raise ValueError("bop: no current-account sheet")
    flow_row = xlsx.find_row(ws, "credit", column=ws.max_column - 2, limit=8)
    if flow_row is None:
        flow_row = next(
            (
                r
                for r in range(1, 9)
                if any(
                    xlsx.key(ws.cell(r, c).value) == "credit"
                    for c in range(2, ws.max_column + 1)
                )
            ),
            None,
        )
    if flow_row is None:
        raise ValueError("bop: no Credit/Debit/Net row")
    quarters = xlsx.forward_fill(ws, flow_row - 1)

    columns: list[tuple[str, str, int]] = []
    for col in range(2, ws.max_column + 1):
        flow = xlsx.key(ws.cell(flow_row, col).value)
        label = xlsx.norm(quarters[col - 1]) if quarters[col - 1] else ""
        if flow not in ("credit", "debit", "net") or not label:
            continue
        year = "".join(ch for ch in label[:4] if ch.isdigit())
        quarter = next((q for q in "1234" if f"{q}" in label.split("-")[-1]), None)
        if year and quarter:
            columns.append((f"{year}-Q{quarter}", flow, col))
    if not columns:
        raise ValueError("bop: no quarter columns")
    keep = sorted({period for period, _, _ in columns})[-BOP_QUARTERS:]

    lines = []
    for row in range(flow_row + 1, ws.max_row + 1):
        depth, label = None, ""
        for col in range(1, 9):
            text = xlsx.norm(ws.cell(row, col).value)
            if text:
                depth, label = col, text
                break
        if not label:
            continue
        flows: dict[str, dict[str, float]] = {}
        for period, flow, col in columns:
            if period not in keep:
                continue
            value = xlsx.num(ws.cell(row, col).value)
            if value is not None:
                flows.setdefault(flow, {})[period] = value
        if flows.get("net"):
            lines.append(
                {
                    "label": label,
                    "depth": depth,
                    "net": xlsx.series(flows["net"]),
                }
            )
    return {"quarters": keep, "lines": lines}


def parse_trade(wb, direction: str) -> dict:
    """Monthly exports or imports in USD, by category.

    Sheet names embed the covered years and roll over each January, so the
    sheet is found by the stable words "in usd" instead.
    """
    ws = next(
        (
            wb[n]
            for n in wb.sheetnames
            if "inusd" in xlsx.key(n) and "sitc" not in xlsx.key(n) and "2006" not in n
        ),
        None,
    )
    if ws is None:
        raise ValueError(f"{direction}: no 'In USD' sheet in {wb.sheetnames}")

    # The header mixes real date cells with text ("Jan-26 (b)") partway along,
    # so it is read type-agnostically — matching datetimes alone truncated the
    # series at 2018-12 while the workbook ran to the current month.
    header = next(
        (r for r in range(1, 12) if len(xlsx.month_columns(ws, r)) >= 6),
        None,
    )
    if header is None:
        raise ValueError(f"{direction}: no dated header row")
    columns = xlsx.month_columns(ws, header)
    keep = set(sorted(columns)[-TRADE_MONTHS:])

    categories = []
    for row in range(header + 1, ws.max_row + 1):
        label = xlsx.norm(ws.cell(row, 1).value)
        if not label:
            continue
        points = xlsx.series(
            {t: xlsx.num(ws.cell(row, c).value) for t, c in columns.items() if t in keep}
        )
        if points:
            categories.append({"label": label, "points": points})
    if not categories:
        raise ValueError(f"{direction}: no category rows")
    return {"unit": "USD mn", "categories": categories}


def total_series(trade: dict) -> list[dict]:
    """The workbook's own total row, matched on its label."""
    for category in trade["categories"]:
        if xlsx.key(category["label"]).startswith("total"):
            return category["points"]
    return []
