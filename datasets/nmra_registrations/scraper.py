"""NMRA valid-registrations: date-stamped XLS link re-discovered from the homepage."""

import csv
import re
import sys
import tempfile
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin, unquote, urlparse

from pipeline.doc import Doc
from pipeline.http import get
from pipeline.store import Store

from .parser import parse_xls, summarize

DATASET = "nmra_registrations"
HOME = "https://www.nmra.gov.lk/"


class RegistrationLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.href = None
        self.label = ""

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.label = ""

    def handle_data(self, data):
        if self.href:
            self.label += data + " "

    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            self.links.append((self.href, self.label))
            self.href = None


def discover_registration(html: str) -> tuple[str, str]:
    parser = RegistrationLinks()
    parser.feed(html)
    candidates = []
    for href, label in parser.links:
        url = urljoin(HOME, href)
        name = unquote(urlparse(url).path)
        if urlparse(url).scheme not in ("http", "https") or not re.search(r"\.xlsx?$", name, re.I):
            continue
        if not re.search(r"registered\s+(?:medicines|drugs)|valid.*(?:registration|medicine|drug)|registration.*valid", label + " " + name, re.I):
            continue
        stamps = re.findall(r"(\d{2})[.\-_](\d{2})[.\-_](\d{4})", name)
        if not stamps:
            continue
        day, month, year = map(int, stamps[-1])
        try:
            published = date(year, month, day).isoformat()
        except ValueError:
            continue
        candidates.append((published, url))
    if not candidates:
        raise RuntimeError("NMRA dated registration workbook link not found")
    published, url = max(candidates)
    return url, published


def run(_budget_seconds: float = 300) -> int:
    store = Store()
    html = get(HOME).text
    url, doc_date = discover_registration(html)
    doc_id = doc_date.replace("-", "")
    probe = Doc(DATASET, doc_id, doc_date, url, sha256="")
    if store.exists(probe):
        print(f"{doc_date}: already scraped")
        store.regenerate_indexes(DATASET)
        return 0
    payload = get(url, timeout=120).content
    if not payload.startswith((b"PK", bytes.fromhex("D0CF11E0"))):
        raise ValueError("NMRA download is not an XLS/XLSX workbook")
    with tempfile.NamedTemporaryFile(suffix=".xls") as tmp:
        tmp.write(payload)
        tmp.flush()
        header, rows = parse_xls(tmp.name)
    if not rows or not any("generic" in h.lower() for h in header):
        raise ValueError("NMRA workbook has no medicine registration rows")
    clean = {"date": doc_date, **summarize(header, rows)}
    doc_dir = store.write_doc(
        Doc(DATASET, doc_id, doc_date, url, Doc.sha256_of(payload)), payload, "original.xlsx" if payload.startswith(b"PK") else "original.xls", clean
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
