"""CBSL Weekly Economic Indicators — Friday-dated deterministic URL, walk back 4 weeks."""

import sys
from datetime import date, timedelta

from pipeline.doc import Doc
from pipeline.http import get_pdf
from pipeline.store import Store

from .parser import parse_pdf

DATASET = "cbsl_weekly"
URL_TEMPLATE = (
    "https://www.cbsl.gov.lk/sites/default/files/cbslweb_documents/statistics/wei/WEI_{stamp}_e.pdf"
)


def last_fridays(count: int) -> list[date]:
    d = date.today()
    d -= timedelta(days=(d.weekday() - 4) % 7)  # most recent Friday
    return [d - timedelta(weeks=i) for i in range(count)]


def run(_budget_seconds: float = 300) -> int:
    store = Store()
    new_docs = 0
    for friday in last_fridays(4):
        stamp = friday.strftime("%Y%m%d")
        url = URL_TEMPLATE.format(stamp=stamp)
        probe = Doc(DATASET, stamp, friday.isoformat(), url, sha256="")
        if store.exists(probe):
            continue
        payload = get_pdf(url)
        if payload is None:
            print(f"{friday}: no edition (404)")
            continue
        try:
            clean = {"week_ending": friday.isoformat(), **parse_pdf(payload)}
        except ValueError as err:
            print(f"{friday}: parse failed, skipping ({err})")
            continue
        store.write_doc(Doc(DATASET, stamp, friday.isoformat(), url, Doc.sha256_of(payload)), payload, "original.pdf", clean)
        print(f"{friday}: reserves={clean.get('reserves_usd_mn')} exports={clean.get('exports_usd_mn')}")
        new_docs += 1
    store.regenerate_indexes(DATASET)
    print(f"done: {new_docs} new docs")
    return new_docs


if __name__ == "__main__":
    run(float(sys.argv[1]) if len(sys.argv) > 1 else 300)
