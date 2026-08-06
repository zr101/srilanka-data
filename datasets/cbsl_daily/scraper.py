"""CBSL Daily Economic Indicators scraper.

Deterministic URL per working day; walks back N days, downloads missing
editions, parses, and writes layered docs + regenerated indexes.
Run: PYTHONPATH=src:. python -m datasets.cbsl_daily.scraper [days]
"""

import sys
from datetime import date, timedelta

from pipeline.doc import Doc
from pipeline.http import get_pdf
from pipeline.runner import TimeBudget
from pipeline.store import Store

DATASET = "cbsl_daily"
URL_TEMPLATE = (
    "https://www.cbsl.gov.lk/sites/default/files/daily_economic_indicators_{stamp}_e.pdf"
)

from .parser import parse_pdf  # noqa: E402


def run(days_back: int = 10, budget_seconds: float = 600) -> int:
    store = Store()
    budget = TimeBudget(budget_seconds)
    new_docs = 0
    today = date.today()
    for offset in range(days_back):
        if budget.expired:
            print("time budget reached; resuming next run")
            break
        day = today - timedelta(days=offset)
        if day.weekday() >= 5:  # no weekend editions
            continue
        stamp = day.strftime("%Y%m%d")
        url = URL_TEMPLATE.format(stamp=stamp)
        probe = Doc(DATASET, stamp, day.isoformat(), url, sha256="")
        if store.exists(probe):
            continue
        payload = get_pdf(url)
        if payload is None:
            print(f"{day}: no edition (404)")
            continue
        clean = {"date": day.isoformat(), **parse_pdf(payload)}
        doc = Doc(DATASET, stamp, day.isoformat(), url, Doc.sha256_of(payload))
        store.write_doc(doc, payload, "original.pdf", clean)
        print(f"{day}: scraped (tbill 364d = {clean['tbill']['d364']})")
        new_docs += 1
    store.regenerate_indexes(DATASET)
    print(f"done: {new_docs} new docs")
    return new_docs


if __name__ == "__main__":
    run(days_back=int(sys.argv[1]) if len(sys.argv) > 1 else 10)
