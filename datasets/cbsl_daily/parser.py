"""CBSL Daily Economic Indicators parser.

The PDF's text layer is z-order scrambled (labels far from values in the
stream), but the page is a fixed single-page template, so extraction is
coordinate-based: pdfplumber words paired by row (same y) and x-band.
Verified against 2026 editions; snapshot-tested in tests/.
"""

import io
import re

import pdfplumber

NUM_RE = re.compile(r"^-?\d{1,3}(,\d{3})*(\.\d+)?%?$")

# x-bands for the T-bill panel's two value columns (page is 595pt wide)
TBILL_PRIMARY_X = (415, 478)
TBILL_SECONDARY_X = (479, 555)
TBILL_LABEL_X = (330, 400)


class Word:
    def __init__(self, raw: dict):
        self.text: str = raw["text"]
        self.x: float = raw["x0"]
        self.y: float = raw["top"]


def _num(text: str) -> float:
    return float(text.replace(",", "").replace("%", ""))


def _same_row(words: list[Word], y: float, tol: float = 5.0) -> list[Word]:
    return sorted([w for w in words if abs(w.y - y) <= tol], key=lambda w: w.x)


def _value_after_label(row: list[Word], label: str) -> float | None:
    for i, w in enumerate(row):
        if w.text == label:
            for nxt in row[i + 1 :]:
                if NUM_RE.match(nxt.text):
                    return _num(nxt.text)
    return None


def _tbill_row_value(words: list[Word], tenor: str, x_band: tuple[float, float]) -> float | None:
    for w in words:
        if w.text == tenor and TBILL_LABEL_X[0] <= w.x <= TBILL_LABEL_X[1]:
            # confirm it's the "<tenor> Day" label, not a stray number
            row = _same_row(words, w.y)
            if not any(r.text.startswith("Day") for r in row):
                continue
            for cand in row:
                if x_band[0] <= cand.x <= x_band[1] and NUM_RE.match(cand.text):
                    return _num(cand.text)
    return None


def parse_pdf(payload: bytes) -> dict:
    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        words = [Word(w) for w in pdf.pages[0].extract_words()]

    tbill = {
        tenor: _tbill_row_value(words, str(days), TBILL_PRIMARY_X)
        for tenor, days in (("d91", 91), ("d182", 182), ("d364", 364))
    }
    tbill_secondary = {
        tenor: _tbill_row_value(words, str(days), TBILL_SECONDARY_X)
        for tenor, days in (("d91", 91), ("d182", 182), ("d364", 364))
    }

    # OPR / SRR / AWPR share one row: "Policy Rate (OPR): 8.75% SRR: 2.00% Weekly AWPR: 10.67%"
    opr = srr = awpr = None
    for w in words:
        if w.text == "(OPR):":
            row = _same_row(words, w.y)
            opr = _value_after_label(row, "(OPR):")
            srr = _value_after_label(row, "SRR:")
            awpr = _value_after_label(row, "AWPR:")
            break

    # Overnight liquidity: label block on the left, value to its right on the same row
    liquidity = None
    for w in words:
        if w.text == "Liquidity" and w.x < 150:
            row = _same_row(words, w.y, tol=8)
            for cand in row:
                if cand.x > 150 and cand.x < 340 and NUM_RE.match(cand.text):
                    liquidity = _num(cand.text)
                    break
            break

    result = {
        "tbill": tbill,
        "tbill_secondary": tbill_secondary,
        "opr": opr,
        "srr": srr,
        "awpr": awpr,
        "overnight_liquidity_rs_bn": liquidity,
    }

    missing = [k for k, v in tbill.items() if v is None]
    if missing or opr is None:
        raise ValueError(f"cbsl_daily parse incomplete: tbill missing {missing}, opr={opr}")
    for name, value in {**tbill, "opr": opr}.items():
        if not 0 < value < 50:
            raise ValueError(f"cbsl_daily implausible {name}={value}")
    try:
        result.update(parse_panels(payload))
    except Exception as err:  # panels are additive; rates are the core contract
        result["_panels_error"] = str(err)
    return result


def rebuild(payload: bytes, _existing: dict) -> dict:
    clean = dict(_existing)
    clean.update(parse_pdf(payload))
    return clean


# --- Full-panel extraction (audit coordinate map, 2026-08-08) ---

def _panel_lines(chars: list[dict], x0: float, y0: float, x1: float, y1: float) -> list[dict]:
    """Char-level line reconstruction inside a bbox: [{y, x, text}] sorted by y.
    Only upright chars (rotated axis labels excluded)."""
    sel = [c for c in chars if c.get("upright") and x0 <= (c["x0"] + c["x1"]) / 2 <= x1 and y0 <= c["top"] <= y1]
    rows: dict[int, list[dict]] = {}
    for c in sel:
        rows.setdefault(round(c["top"] / 3), []).append(c)
    out = []
    for k in sorted(rows):
        cs = sorted(rows[k], key=lambda c: c["x0"])
        s, prev = "", None
        for c in cs:
            if prev is not None and c["x0"] - prev > 1.5:
                s += " "
            s += c["text"]
            prev = c["x1"]
        out.append({"y": min(c["top"] for c in cs), "x": min(c["x0"] for c in cs), "text": s})
    return out


def _num_clean(t: str) -> float:
    return float(t.replace(",", "").replace(" ", ""))


def parse_panels(payload: bytes) -> dict:
    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        chars = pdf.pages[0].chars

    out: dict = {}

    # 1) macro strip: GDP standalone pct; NCPI/CCPI values render per-char —
    # de-space the whole strip and regex by label
    strip = _panel_lines(chars, 30, 40, 595, 100)
    for l in strip:
        m = re.match(r"^(-?\d{1,2}\.\d)%$", l["text"].strip())
        if m and l["x"] < 220:
            out["gdp_growth_pct"] = float(m.group(1))
    despaced = "".join(l["text"] for l in strip).replace(" ", "")
    for label, key in (("NCPI", "ncpi_yoy_pct"), ("CCPI", "ccpi_yoy_pct")):
        m = re.search(label + r"Y-o-YChange:([A-Za-z]+)(\d{4})(-?\d{1,2}\.\d)%", despaced)
        if m:
            out[key] = float(m.group(3))
            out[key.replace("_yoy_pct", "_month")] = m.group(1)

    # 2) TT exchange rates: currency labels y-matched to buy/sell number pairs
    fx_lines = _panel_lines(chars, 36, 100, 292, 192)
    pairs, labels = [], []
    for l in fx_lines:
        pm = re.match(r"^([\d,]+\.\d{2,4}) ([\d,]+\.\d{2,4})$", l["text"].strip())
        lm = re.match(r"^(USD|GBP|EUR|JPY)(?: ([\d,]+\.\d{2,4}) ([\d,]+\.\d{2,4}))?$", l["text"].strip())
        if lm:
            labels.append({"y": l["y"], "cur": lm.group(1),
                           "pair": (_num_clean(lm.group(2)), _num_clean(lm.group(3))) if lm.group(2) else None})
        elif pm:
            pairs.append({"y": l["y"], "pair": (_num_clean(pm.group(1)), _num_clean(pm.group(2)))})
    fx = {}
    for lab in labels:
        pair = lab["pair"]
        if pair is None and pairs:
            nearest = min(pairs, key=lambda p: abs(p["y"] - lab["y"]))
            if abs(nearest["y"] - lab["y"]) <= 10:
                pair = nearest["pair"]
        if pair:
            fx[lab["cur"].lower()] = {"tt_buy": pair[0], "tt_sell": pair[1]}
    if fx:
        out["fx_tt"] = fx

    # 3) USD spot annotation (chart's latest-value label)
    for l in _panel_lines(chars, 220, 195, 330, 240):
        m = re.match(r"^(\d{3}\.\d{2})", l["text"].strip())
        if m:
            out["usd_spot"] = float(m.group(1))
            break

    # 4) CIC & reserve money (Rs mn; two date columns, take both)
    for l in _panel_lines(chars, 292, 100, 565, 168):
        m = re.search(r"([\d,]{7,}\.\d{2}) ([\d,]{7,}\.\d{2})$", l["text"])
        if m:
            key = "cic_rs_mn" if "Circulation" in l["text"] or "cic_rs_mn" not in out else "reserve_money_rs_mn"
            if "Circulation" in l["text"]:
                key = "cic_rs_mn"
            elif "Money" in l["text"] or "reserve_money_rs_mn" not in out:
                key = "reserve_money_rs_mn"
            out[key] = {"previous": _num_clean(m.group(1)), "latest": _num_clean(m.group(2))}

    # 5) share market table (right column of the share panel)
    sm = {}
    for l in _panel_lines(chars, 318, 440, 565, 545):
        t = l["text"]
        m = re.search(r"([\d,]+\.?\d*)\s*$", t)
        if not m:
            continue
        v = _num_clean(m.group(1))
        if re.search(r"Turnover", t, re.I):
            sm["turnover_rs_mn"] = v
        elif re.search(r"Market Cap", t, re.I):
            sm["market_cap_rs_bn"] = v
        elif re.search(r"\bPE\b|P/E", t, re.I):
            sm["pe_ratio"] = v
        elif re.search(r"Purchases", t, re.I):
            sm["foreign_purchases_rs_mn"] = v
        elif re.search(r"Sales", t, re.I):
            sm["foreign_sales_rs_mn"] = v
    if sm:
        out["share_market"] = sm

    # 6) CPC pump prices (per-character digit strip) — cross-checks ceypetco
    fuel_text = " ".join(l["text"] for l in _panel_lines(chars, 30, 552, 565, 590))
    fuel_text_ns = fuel_text.replace(" ", "")
    fm = {}
    for label, key in (("Petrol\\(?92", "petrol92"), ("Petrol\\(?95", "petrol95"), ("Diesel", "diesel"), ("Kerosene", "kerosene")):
        m = re.search(label + r"[^\d]{0,25}(\d{3}\.\d{2})", fuel_text_ns, re.I)
        if m:
            fm[key] = float(m.group(1))
    if fm:
        out["pump_prices_rs"] = fm

    # 7) crude & Singapore Platts: header line then a 6-number columnar row
    crude_lines = _panel_lines(chars, 30, 580, 330, 670)
    for i, l in enumerate(crude_lines):
        if "Brent" in l["text"] and "WTI" in l["text"]:
            for nxt in crude_lines[i + 1 : i + 3]:
                nums = re.findall(r"[\d,]+\.\d{2}", nxt["text"])
                if len(nums) >= 6:
                    vals = [_num_clean(n) for n in nums[:6]]
                    out["crude_usd"] = {"brent": vals[0], "wti": vals[1], "opec": vals[2]}
                    out["platts_usd"] = {"petrol": vals[3], "diesel": vals[4], "kerosene": vals[5]}
                    break
            break

    # 8) electricity: total GWh, peak MW, generation mix %
    elec = {}
    mix = {}
    pending = None
    for l in _panel_lines(chars, 322, 550, 565, 748):
        t = l["text"]
        m2 = re.search(r"([\d,]+\.?\d*) ([\d,]+\.?\d*)$", t)
        if re.search(r"Total Energy", t, re.I):
            pending = "total_gwh"
            if m2:
                elec["total_gwh"] = _num_clean(m2.group(2))
                pending = None
        elif re.search(r"Peak Demand", t, re.I):
            pending = "peak_mw"
            if m2 and not t.strip().startswith("Peak") is False:
                pass
        elif m2 and pending and re.match(r"^[\d,]+\.?\d* [\d,]+\.?\d*$", t.strip()):
            elec[pending] = _num_clean(m2.group(2))
            pending = None
        mm = re.match(r"^([\d.]+) (Thermal Coal|Thermal Oil|Hydro|Wind|Solar|Biomass)$", t.strip(), re.I)
        if mm:
            mix[mm.group(2).lower().replace(" ", "_")] = float(mm.group(1))
    if mix:
        elec["generation_mix_pct"] = mix
    if elec:
        out["electricity"] = elec

    return out
