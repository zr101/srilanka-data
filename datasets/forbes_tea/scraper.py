"""Forbes & Walker weekly tea auction quantities & averages (year file, updated weekly)."""

import re
import sys
from datetime import date

from pipeline.doc import Doc
from pipeline.http import get, get_pdf
from pipeline.store import Store

from .parser import parse_pdf

DATASET = "forbes_tea"
LISTING = "https://www.forbestea.com/statistics-weekly-tea-auction-quantities-&-averages"


def run(_budget_seconds: float = 300) -> int:
    store = Store()
    year = date.today().year
    html = get(LISTING).text
    links = re.findall(r'href="(https?://[^"]*Quantities[^"]*\.pdf)"', html)
    target = next((l.replace("&amp;", "&") for l in links if str(year) in l), None)
    if not target:
        raise RuntimeError(f"no {year} quantities PDF on Forbes listing")
    payload = get_pdf(target.replace(" ", "%20"))
    if payload is None:
        raise RuntimeError("Forbes PDF 404")
    clean = parse_pdf(payload, year)
    doc_id = clean["latest"]["sale_date"].replace("-", "")
    doc_date = clean["latest"]["sale_date"]
    probe = Doc(DATASET, doc_id, doc_date, target, sha256="")
    if store.exists(probe):
        print(f"{doc_date}: already scraped")
        store.regenerate_indexes(DATASET)
        return 0
    store.write_doc(Doc(DATASET, doc_id, doc_date, target, Doc.sha256_of(payload)), payload, "original.pdf", clean)
    store.regenerate_indexes(DATASET)
    print(f"{doc_date}: {len(clean['sales'])} sales, latest avg Rs {clean['latest']['avg_rs']['total']}")
    return 1


if __name__ == "__main__":
    run(float(sys.argv[1]) if len(sys.argv) > 1 else 300)
