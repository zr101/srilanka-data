"""Weekly Epidemiological Report: listing page → newest Vol/No PDFs."""

import re
import sys
from datetime import date

from pipeline.doc import Doc
from pipeline.http import get, get_pdf
from pipeline.runner import TimeBudget
from pipeline.store import Store

from .parser import parse_pdf

DATASET = "wer"
LISTING = "https://www.epid.gov.lk/weekly-epidemiological-report/weekly-epidemiological-report"
LINK_RE = re.compile(r'href="(https?://[^"]*/pdfs/[^"]*Vol_(\d+)_no_(\d+)-english\.pdf)"', re.I)


def run(keep_latest: int = 4, budget_seconds: float = 300) -> int:
    store = Store()
    budget = TimeBudget(budget_seconds)
    html = get(LISTING).text
    issues: dict[tuple[int, int], str] = {}
    for url, vol, no in LINK_RE.findall(html):
        issues[(int(vol), int(no))] = url
    new_docs = 0
    for (vol, no) in sorted(issues, reverse=True)[:keep_latest]:
        if budget.expired:
            break
        url = issues[(vol, no)]
        doc_id = f"vol{vol:03d}-no{no:02d}"
        doc_date = date.today().isoformat()  # listing carries no date; issue id is canonical
        probe = Doc(DATASET, doc_id, doc_date, url, sha256="")
        if any(store.dataset_dir(DATASET).rglob(f"{doc_id}/doc.json")):
            continue
        payload = get_pdf(url)
        if payload is None:
            continue
        clean = {"volume": vol, "issue": no, **parse_pdf(payload)}
        store.write_doc(Doc(DATASET, doc_id, doc_date, url, Doc.sha256_of(payload)), payload, "original.pdf", clean)
        print(f"Vol {vol} No {no}: {len(clean['districts'])} districts")
        new_docs += 1
    store.regenerate_indexes(DATASET)
    print(f"done: {new_docs} new docs")
    return new_docs


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 4)
