"""Treasury auction results: buildId → year listing JSON → new English releases."""

import re
from html import unescape
import sys
from datetime import date

from pipeline.doc import Doc
from pipeline.http import USER_AGENT, get
from pipeline.runner import TimeBudget
from pipeline.store import Store

from .parser import parse_pdf

DATASET = "tbill_auctions"
TREASURY = "https://www.treasury.gov.lk"


def publication_links(listing: dict) -> list[dict]:
    props = listing.get("pageProps", {})
    links = list(props.get("pageData", {}).get("links", []))
    for section in props.get("sections", []):
        for paragraph in re.findall(r"<p\b[^>]*>(.*?)</p>", section.get("html", ""), re.S | re.I):
            text = unescape(re.sub(r"<[^>]+>", " ", paragraph))
            stamp = re.search(r"\d{2}\.\d{2}\.\d{4}", text)
            if not stamp:
                continue
            for href, label in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', paragraph, re.S | re.I):
                label = unescape(re.sub(r"<[^>]+>", " ", label))
                file_id = re.search(r"/api/file/([a-f0-9-]{36})", href, re.I)
                if file_id and re.search(r"\bEnglish\b", label, re.I):
                    links.append({"urlType": "file", "link": file_id.group(1), "title": stamp.group(0) + " " + label})
    def sort_key(link):
        m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", link.get("title", ""))
        return (m.group(3), m.group(2), m.group(1)) if m else ("", "", "")
    return sorted({link.get("link"): link for link in links}.values(), key=sort_key, reverse=True)


def run(budget_seconds: float = 300) -> int:
    store = Store()
    budget = TimeBudget(budget_seconds)
    build_id = re.search(r'"buildId":"([^"]+)"', get(f"{TREASURY}/").text).group(1)
    year = date.today().year
    listing = get(
        f"{TREASURY}/_next/data/{build_id}/web/result-treasury-bills/section/{year}.json"
    ).json()
    links = publication_links(listing)
    if not links:
        raise ValueError("Treasury listing contains no auction releases")
    new_docs = 0
    for link in links:
        if budget.expired or new_docs >= 12:
            break
        title = link.get("title", "")
        if link.get("urlType") != "file" or not re.search(r"(press release\s+E\b|\bE\s+T\s*Bill|English)", title, re.I):
            continue
        date_m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", title)
        if not date_m:
            continue
        doc_date = f"{date_m.group(3)}-{date_m.group(2)}-{date_m.group(1)}"
        uuid = link["link"]
        doc_id = f"{doc_date.replace('-', '')}-{uuid[:8]}"
        url = f"{TREASURY}/api/file/{uuid}"
        probe = Doc(DATASET, doc_id, doc_date, url, sha256="")
        if store.exists(probe):
            continue
        payload = get(url).content
        if not payload.startswith(b"%PDF"):
            raise ValueError(f"Treasury release is not a PDF: {title}")
        clean = {"date": doc_date, "title": title, **parse_pdf(payload)}
        store.write_doc(
            Doc(DATASET, doc_id, doc_date, url, Doc.sha256_of(payload)),
            payload,
            "original.pdf",
            clean,
        )
        print(f"{doc_date}: {clean['results']}")
        new_docs += 1
    store.regenerate_indexes(DATASET)
    print(f"done: {new_docs} new docs")
    return new_docs


if __name__ == "__main__":
    run(float(sys.argv[1]) if len(sys.argv) > 1 else 300)
