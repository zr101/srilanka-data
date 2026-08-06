"""NMRA valid-registrations: date-stamped XLS link re-discovered from the homepage."""

import csv
import io
import re
import sys
import tempfile

from pipeline.doc import Doc
from pipeline.http import get
from pipeline.store import Store

from .parser import parse_xls, summarize

DATASET = "nmra_registrations"
HOME = "https://www.nmra.gov.lk/"


def run(_budget_seconds: float = 300) -> int:
    store = Store()
    html = get(HOME).text
    link_m = re.search(r'https://[^"]*valid[^"]*\.xls', html, re.I)
    if not link_m:
        raise RuntimeError("NMRA registrations XLS link not found on homepage")
    url = link_m.group(0)
    date_m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", url)
    if not date_m:
        raise RuntimeError(f"no date stamp in NMRA XLS filename: {url}")
    doc_date = f"{date_m.group(3)}-{date_m.group(2)}-{date_m.group(1)}"
    doc_id = doc_date.replace("-", "")
    probe = Doc(DATASET, doc_id, doc_date, url, sha256="")
    if store.exists(probe):
        print(f"{doc_date}: already scraped")
        store.regenerate_indexes(DATASET)
        return 0
    payload = get(url, timeout=120).content
    with tempfile.NamedTemporaryFile(suffix=".xls") as tmp:
        tmp.write(payload)
        tmp.flush()
        header, rows = parse_xls(tmp.name)
    clean = {"date": doc_date, **summarize(header, rows)}
    doc_dir = store.write_doc(
        Doc(DATASET, doc_id, doc_date, url, Doc.sha256_of(payload)), payload, "original.xls", clean
    )
    with open(doc_dir / "registrations.tsv", "w", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(header)
        writer.writerows(rows)
    store.regenerate_indexes(DATASET)
    print(f"{doc_date}: {clean['total_registrations']} registrations")
    return 1


if __name__ == "__main__":
    run(float(sys.argv[1]) if len(sys.argv) > 1 else 300)
