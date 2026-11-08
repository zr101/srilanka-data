"""SLTDA weekly arrivals reports (posted monthly-bundled) from the yearly listing."""

import calendar
import re
import sys
from datetime import date

from pipeline.doc import Doc
from pipeline.http import get, get_pdf
from pipeline.runner import TimeBudget
from pipeline.store import Store

from .parser import parse_pdf, reporting_date

DATASET = "sltda_arrivals"
MONTH_NUM = {m: i for i, m in enumerate(calendar.month_name) if m}


def run(budget_seconds: float = 300) -> int:
    store = Store()
    budget = TimeBudget(budget_seconds)
    year = date.today().year
    listing = get(f"https://www.sltda.gov.lk/en/weekly-tourist-arrivals-reports-{year}").text
    urls = re.findall(r'href="(https?://[^"]*Weekly[^"]*\.pdf)"', listing)
    if not urls:
        raise ValueError("SLTDA listing contains no weekly reports")
    new_docs = 0
    for url in reversed(list(dict.fromkeys(urls))):
        if budget.expired:
            break
        month_m = re.search(rf"({'|'.join(MONTH_NUM)})_(\d{{4}})", url)
        if not month_m:
            continue
        month, yr = MONTH_NUM[month_m.group(1)], int(month_m.group(2))
        doc_date = f"{yr}-{month:02d}-{calendar.monthrange(yr, month)[1]:02d}"
        doc_id = f"{yr}{month:02d}"
        probe = Doc(DATASET, doc_id, doc_date, url, sha256="")
        if store.exists(probe) and (yr, month) < (date.today().year, date.today().month):
            continue
        payload = get_pdf(url)
        if payload is None:
            continue
        doc_date = reporting_date(payload)
        doc_id = f"{yr}{month:02d}-{Doc.sha256_of(payload)[:12]}"
        if store.exists(Doc(DATASET, doc_id, doc_date, url, sha256="")):
            continue
        clean = {"reporting_date": doc_date, "period": f"{yr}-{month:02d}", **parse_pdf(payload)}
        store.write_doc(Doc(DATASET, doc_id, doc_date, url, Doc.sha256_of(payload)), payload, "original.pdf", clean)
        print(f"{yr}-{month:02d}: ytd_total={clean['ytd_total']}")
        new_docs += 1
    store.regenerate_indexes(DATASET)
    print(f"done: {new_docs} new docs")
    return new_docs


if __name__ == "__main__":
    run(float(sys.argv[1]) if len(sys.argv) > 1 else 300)
