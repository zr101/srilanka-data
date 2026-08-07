"""WER disease-by-district table: strictly row-major token stream —
district name followed by exactly 30 numeric tokens (14 diseases × A/B + 2 QC).

Disease column order VERIFIED (audit 2026-08-08) two independent ways: header
glyph geometry, and exact reconciliation of all 28 A/B column sums against the
SRI LANKA total row. Kalmunai is a distinct RDHS region from Ampara — both map
to district LK-52 for geo joins, but `rdhs` is the unique key for aggregation."""

import io
import re

from pypdf import PdfReader

DISEASES = [
    "dengue",
    "dysentery",
    "encephalitis",
    "enteric_fever",
    "food_poisoning",
    "leptospirosis",
    "typhus",
    "viral_hepatitis",
    "human_rabies",
    "chickenpox",
    "meningitis",
    "leishmaniasis",
    "tuberculosis",
    "leprosy",
]

DISTRICT_IDS = {
    "Colombo": "LK-11", "Gampaha": "LK-12", "Kalutara": "LK-13",
    "Kandy": "LK-21", "Matale": "LK-22", "Nuwara Eliya": "LK-23", "NuwaraEliya": "LK-23",
    "Galle": "LK-31", "Hambantota": "LK-33", "Matara": "LK-32",
    "Jaffna": "LK-41", "Kilinochchi": "LK-42", "Mannar": "LK-43",
    "Vavuniya": "LK-44", "Mullaitivu": "LK-45",
    "Batticaloa": "LK-51", "Ampara": "LK-52", "Trincomalee": "LK-53", "Kalmunai": "LK-52",
    "Kurunegala": "LK-61", "Puttalam": "LK-62",
    "Anuradhapura": "LK-71", "Polonnaruwa": "LK-72",
    "Badulla": "LK-81", "Monaragala": "LK-82", "Moneragala": "LK-82",
    "Ratnapura": "LK-91", "Kegalle": "LK-92",
}

NUMERIC_RE = re.compile(r"^-?\d+$|^\d+\.\d+$")


def _tokens(payload: bytes) -> list[str]:
    # pypdf, not pdfplumber: the district table's content stream is invisible
    # to pdfplumber's extractor but decodes fine here (verified Vol 53 No 26).
    out: list[str] = []
    for page in PdfReader(io.BytesIO(payload)).pages:
        out.extend(t for t in (page.extract_text() or "").split() if t)
    return out


def parse_pdf(payload: bytes) -> dict:
    tokens = _tokens(payload)
    districts = []
    total_row = None
    i = 0
    while i < len(tokens):
        token = tokens[i]
        name = None
        if token in DISTRICT_IDS:
            name = "Nuwara Eliya" if token == "NuwaraEliya" else token
        elif token == "Nuwara" and i + 1 < len(tokens) and tokens[i + 1].startswith("Eliya"):
            name = "Nuwara Eliya"
            i += 1
        elif token in ("SRILANKA", "SRI") and total_row is None:
            j = i + (2 if token == "SRI" else 1)
            values: list[int | None] = []
            while j < len(tokens) and len(values) < 30:
                t = tokens[j]
                if NUMERIC_RE.match(t):
                    values.append(int(float(t)))
                elif t in ("NR", "-", "–"):
                    values.append(None)
                else:
                    break
                j += 1
            if len(values) == 30:
                total_row = {
                    DISEASES[k]: {"week": values[2 * k], "cumulative": values[2 * k + 1]}
                    for k in range(14)
                }
                i = j
                continue
        if name:
            values: list[int | None] = []
            j = i + 1
            while j < len(tokens) and len(values) < 30:
                t = tokens[j]
                if NUMERIC_RE.match(t):
                    values.append(int(float(t)))
                elif t in ("NR", "-", "–"):
                    values.append(None)
                else:
                    break
                j += 1
            if len(values) == 30:
                diseases = {
                    DISEASES[k]: {"week": values[2 * k], "cumulative": values[2 * k + 1]}
                    for k in range(14)
                }
                districts.append(
                    {
                        "district": name,
                        "rdhs": name,  # unique aggregation key (Kalmunai ≠ Ampara)
                        "district_id": DISTRICT_IDS[name.replace(" ", "") if name == "Nuwara Eliya" else name],
                        "diseases": diseases,
                        "timeliness_pct": values[28],
                        "completeness_pct": values[29],
                    }
                )
                i = j
                continue
        i += 1
    if len(districts) < 20:
        raise ValueError(f"WER parse found only {len(districts)} district rows")
    # checksum: column sums must reconcile with the SRI LANKA total row (proven exact)
    # vol053-no24 diagnosed 2026-08-07: correctly rejected, not a parser bug — 13/14
    # diseases reconcile exactly on that same row (rules out column/token shift), the
    # raw "11" token is clean with no fusion artifact, and 3 of the 4 surrounding
    # editions reconcile on every disease. The source PDF's own printed total row
    # undercounts leishmaniasis (115 districts vs 11 total) — a one-off compilation
    # error upstream. Leave quarantined; do not special-case this edition.
    if total_row:
        for disease in DISEASES:
            col_sum = sum(d["diseases"][disease]["week"] or 0 for d in districts)
            expected = total_row[disease]["week"]
            if expected is not None and col_sum != expected:
                raise ValueError(f"WER checksum failed for {disease}: Σdistricts={col_sum} != total={expected}")
    # p4 Table 2 (vaccine-preventable diseases) + malaria line
    vpd, malaria = [], None
    try:
        from pypdf import PdfReader as _PR
        pages = _PR(io.BytesIO(payload)).pages
        for page in pages:
            t = page.extract_text() or ""
            if "Vaccine Preventable" in t:
                vpd, malaria = parse_table2(t)
                break
    except Exception:
        pass  # Table 2 is additive; the district table remains the core contract
    # p2 rotating side table (caption-driven; not every edition carries one)
    side_table = None
    try:
        from pypdf import PdfReader as _PR2
        for page in _PR2(io.BytesIO(payload)).pages:
            side_table = parse_side_table(page.extract_text() or "")
            if side_table:
                break
    except Exception:
        pass  # additive, same as Table 2 above
    return {
        "districts": districts,
        "total": total_row,
        "vaccine_preventable": vpd,
        "malaria_cases_month": malaria,
        "side_table": side_table,
    }


# --- p4 Table 2: Selected Vaccine Preventable Diseases & AFP ---

VPD_NAMES = [
    "AFP", "Diphtheria", "Mumps", "Measles", "Rubella", "CRS", "Tetanus",
    "Neonatal Tetanus", "Japanese Encephalitis", "Whooping Cough", "Tuberculosis",
]
_VPD_ROW = re.compile(r"^([A-Za-z ]+?)\d?\s+((?:\d{1,3}\s+){12}\d{1,3})\s*(-?[\d.]+)\s*%$")
_NUMS_ONLY = re.compile(r"^((?:\d{1,3}\s+){12}\d{1,3})\s*(-?[\d.]+)\s*%$")
_PCT_ONLY = re.compile(r"^(-?[\d.]+)\s*%$")

PROVINCES = ["W", "C", "S", "N", "E", "NW", "NC", "U", "Sab"]


def _vpd_record(name: str, nums: list[int], pct: float | None) -> dict:
    return {
        "disease": name,
        "provinces": dict(zip(PROVINCES, nums[:9])),
        "total_week": nums[9],
        "same_week_last_year": nums[10],
        "to_date": nums[11],
        "to_date_last_year": nums[12],
        "pct_difference": pct,
    }


def parse_table2(page_text: str) -> tuple[list[dict], int | None]:
    lines = [l.strip() for l in page_text.split("\n") if l.strip()]
    rows: list[dict] = []
    pending_pct: float | None = None
    for idx, line in enumerate(lines):
        pm = _PCT_ONLY.match(line)
        if pm:
            pending_pct = float(pm.group(1))
            continue
        m = _VPD_ROW.match(line)
        if m:
            name = m.group(1).strip()
            nums = [int(x) for x in m.group(2).split()]
            rows.append(_vpd_record(name, nums, float(m.group(3))))
            continue
        # split rows: "Neonatal Tetanus2 <13 nums>" (pct came on the line above);
        # values-only line adjacent to a "cephalitis" fragment = Japanese Encephalitis
        nm = re.match(r"^([A-Za-z ]+?)\d?\s+((?:\d{1,3}\s+){12}\d{1,3})\s*$", line)
        if nm:
            rows.append(_vpd_record(nm.group(1).strip(), [int(x) for x in nm.group(2).split()], pending_pct))
            pending_pct = None
            continue
        vm = _NUMS_ONLY.match(line)
        if vm and idx + 1 < len(lines) and "cephalitis" in lines[idx + 1]:
            rows.append(_vpd_record("Japanese Encephalitis", [int(x) for x in vm.group(1).split()], float(vm.group(2))))
    # canonicalize split names (pypdf emits 'cephalitis3' fused with the value row)
    for r in rows:
        low = r["disease"].lower()
        if "cephalitis" in low and "japanese" not in low:
            r["disease"] = "Japanese Encephalitis"
    malaria = None
    mm = re.search(r"Malaria Cases[^,]*,\s*(?:\n\s*)?(\d+)", page_text)
    if mm:
        malaria = int(mm.group(1))
    for r in rows:
        if sum(r["provinces"].values()) != r["total_week"]:
            raise ValueError(f"Table2 {r['disease']}: province sum != total_week")
    return rows, malaria


# --- p2 rotating side table: a small surveillance table appears on the
# document's own "Page 2" (right after the lead article's footer), directly
# below a "Page 2. ... To be Continued…." marker. Its TOPIC rotates across
# editions (only "Water Quality Surveillance" confirmed so far); detect it by
# the structural marker + "Table 1 : <caption>" line, then dispatch on the
# caption text to a per-topic row parser. Unknown captions are skipped, not
# fatal — this field is purely additive, same philosophy as Table 2 above.

_SIDE_TABLE_MARKER_RE = re.compile(r"Page\s*2\s*\.\s*To be Continued", re.I)
_SIDE_TABLE_CAPTION_RE = re.compile(r"Table\s*1\s*:\s*(.+)")
_WATER_QUALITY_ROW_RE = re.compile(r"^([A-Za-z][A-Za-z ]*?)\s+(\d+)\s+(\d+)\s+(\d+|NR)$")


def _parse_water_quality_rows(lines: list[str]) -> list[dict]:
    rows = []
    for line in lines:
        if line.lower().startswith("figure"):
            break  # block ends where the chart annotations begin
        m = _WATER_QUALITY_ROW_RE.match(line)
        if not m:
            continue
        rows.append(
            {
                "area": re.sub(r"\s+", " ", m.group(1)).strip(),  # e.g. "Kalutara NIHS" stays distinct from "Kalutara"
                "moh_areas": int(m.group(2)),
                "no_expected": int(m.group(3)),
                "no_received": None if m.group(4) == "NR" else int(m.group(4)),
            }
        )
    return rows


SIDE_TABLE_HANDLERS = {
    "Water Quality Surveillance": _parse_water_quality_rows,
}


def parse_side_table(page_text: str) -> dict | None:
    marker = _SIDE_TABLE_MARKER_RE.search(page_text)
    if not marker:
        return None
    rest = page_text[marker.end():]
    cap = _SIDE_TABLE_CAPTION_RE.search(rest)
    if not cap:
        return None
    caption = cap.group(1).strip()
    handler = SIDE_TABLE_HANDLERS.get(caption)
    if handler is None:
        return None  # rotating topic we don't have a handler for yet — skip gracefully
    lines = [l.strip() for l in rest[cap.end():].split("\n") if l.strip()]
    rows = handler(lines)
    if not rows:
        return None
    return {"caption": caption, "rows": rows}


def rebuild(payload: bytes, _existing: dict) -> dict:
    clean = dict(_existing)
    clean.update(parse_pdf(payload))
    return clean
