"""WER disease-by-district table: strictly row-major token stream —
district name followed by exactly 30 numeric tokens (14 diseases × A/B + 2 QC).
Dengue is column 1 (verified); remaining disease column names follow the WER
template order and should be re-verified against the header before deep use."""

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
    i = 0
    while i < len(tokens):
        token = tokens[i]
        name = None
        if token in DISTRICT_IDS:
            name = "Nuwara Eliya" if token == "NuwaraEliya" else token
        elif token == "Nuwara" and i + 1 < len(tokens) and tokens[i + 1].startswith("Eliya"):
            name = "Nuwara Eliya"
            i += 1
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
    return {"districts": districts}
