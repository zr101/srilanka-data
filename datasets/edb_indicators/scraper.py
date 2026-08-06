"""EDB Export Performance Indicators ebook (annual, year-templated URL)."""

import sys
from datetime import date

from pipeline.doc import Doc
from pipeline.http import get_pdf
from pipeline.store import Store

from .parser import find_table_text, parse_text

DATASET = "edb_indicators"
URL_TEMPLATE = (
    "https://www.srilankabusiness.com/ebooks/export-performance-indicators-of-sri-lanka-{year}.pdf"
)


def run(_budget_seconds: float = 300) -> int:
    store = Store()
    new_docs = 0
    this_year = date.today().year
    for year in range(this_year - 1, this_year - 4, -1):
        doc_id = str(year)
        doc_date = f"{year}-12-31"
        url = URL_TEMPLATE.format(year=year)
        probe = Doc(DATASET, doc_id, doc_date, url, sha256="")
        if store.exists(probe):
            continue
        payload = get_pdf(url)
        if payload is None:
            print(f"{year}: no edition (404)")
            continue
        try:
            clean = {"report_year": year, **parse_text(find_table_text(payload))}
        except ValueError as err:
            # older editions vary in layout; the latest one is what matters
            print(f"{year}: parse failed, skipping ({err})")
            continue
        store.write_doc(Doc(DATASET, doc_id, doc_date, url, Doc.sha256_of(payload)), payload, "original.pdf", clean)
        print(f"{year}: total {clean['total_usd_mn'][-1]} USD mn")
        new_docs += 1
    store.regenerate_indexes(DATASET)
    print(f"done: {new_docs} new docs")
    return new_docs


if __name__ == "__main__":
    run(float(sys.argv[1]) if len(sys.argv) > 1 else 300)
