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
    return result
