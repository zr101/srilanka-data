"""CBSL Daily Price Report — deterministic daily URL, walk back to fill gaps."""

import sys
from datetime import date, timedelta

from pipeline.doc import Doc
from pipeline.http import get_pdf
from pipeline.store import Store

from .parser import parse_pdf

DATASET = "cbsl_price_report"
URL_TEMPLATE = (
    "https://www.cbsl.gov.lk/sites/default/files/cbslweb_documents/statistics/pricerpt/"
    "price_report_{stamp}_e.pdf"
)
# Published on working days only, so a 10-day window covers weekends and the
# odd public holiday without re-probing the whole archive.
LOOKBACK_DAYS = 10


def run(_budget_seconds: float = 300) -> int:
    store = Store()
    today = date.today()
    new_docs = 0
    for offset in range(LOOKBACK_DAYS):
        day = today - timedelta(days=offset)
        stamp = day.strftime("%Y%m%d")
        url = URL_TEMPLATE.format(stamp=stamp)
        probe = Doc(DATASET, stamp, day.isoformat(), url, sha256="")
        if store.exists(probe):
            continue
        payload = get_pdf(url)
        if payload is None:
            continue  # weekend, holiday, or not yet published
        try:
            clean = {"date": day.isoformat(), **parse_pdf(payload)}
        except ValueError as err:
            print(f"{day}: parse failed, skipping ({err})")
            continue
        store.write_doc(
            Doc(DATASET, stamp, day.isoformat(), url, Doc.sha256_of(payload)),
            payload,
            "original.pdf",
            clean,
        )
        print(f"{day}: {len(clean['items'])} items, {len(clean['highlights'])} highlights")
        new_docs += 1
    store.regenerate_indexes(DATASET)
    print(f"done: {new_docs} new docs")
    return new_docs


if __name__ == "__main__":
    run(float(sys.argv[1]) if len(sys.argv) > 1 else 300)
