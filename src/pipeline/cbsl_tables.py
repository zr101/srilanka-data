"""Shared harvest loop for the CBSL statistical-table families.

Every cbsl_* table dataset does the same four things: discover current workbook
URLs from their listing pages, skip the run when nothing has been republished,
download and validate, then hand the workbooks to a family-specific builder.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone

from . import xlsx
from .doc import Doc
from .store import Store

# CBSL republishes a vintage table-by-table: the listing can link workbooks
# hours-to-days before the files exist (soft-404), with availability flapping
# per member across a day. While a vintage is younger than this, an incomplete
# family is "not fully published yet" (retry next cron), not a failure.
PUBLISH_GRACE_DAYS = 7


def vintage_age_days(doc_id: str, today: date | None = None) -> int:
    """Days since the vintage stamp in a doc id like '20260811'."""
    if today is None:
        today = datetime.now(timezone.utc).date()
    return (today - date(int(doc_id[:4]), int(doc_id[4:6]), int(doc_id[6:8]))).days


@dataclass(frozen=True)
class Source:
    """One workbook within a family."""

    name: str  # output key, e.g. "ccpi"
    listing: str  # statistical-tables page that links it
    needles: tuple[str, ...]  # stable words in the link text
    required: bool = True


def _listings(sources: list[Source]) -> dict[str, dict[str, str]]:
    return {url: xlsx.discover(url) for url in {s.listing for s in sources}}


def resolve(sources: list[Source]) -> dict[str, tuple[str, str]]:
    """{name: (label, url)} for every source found on its listing page."""
    listings = _listings(sources)
    found: dict[str, tuple[str, str]] = {}
    for source in sources:
        hit = xlsx.pick(listings[source.listing], *source.needles)
        if hit:
            found[source.name] = hit
        elif source.required:
            raise ValueError(f"{source.name}: no link matching {source.needles} on {source.listing}")
        else:
            print(f"  {source.name}: not linked (optional), skipping")
    return found


def harvest(
    dataset: str,
    sources: list[Source],
    build: Callable[[dict], dict],
    listing_url: str,
) -> int:
    """Discover → skip-if-unchanged → download → build → store.

    The doc id is the newest vintage stamp across the family's workbooks, so a
    republish of any member starts a new doc while an unchanged family costs
    only the listing-page fetches.
    """
    store = Store()
    resolved = resolve(sources)
    stamps = [xlsx.stamp_of(url) for _, url in resolved.values()]
    stamps = [s for s in stamps if s]
    if not stamps:
        raise ValueError(f"{dataset}: no dated workbooks among {sorted(resolved)}")
    doc_id = max(stamps)
    date = f"{doc_id[:4]}-{doc_id[4:6]}-{doc_id[6:]}"

    probe = Doc(dataset, doc_id, date, listing_url, sha256="")
    if store.exists(probe):
        print(f"{dataset}: {doc_id} already stored, nothing republished")
        store.regenerate_indexes(dataset)
        return 0

    payloads: dict[str, bytes] = {}
    workbooks: dict[str, object] = {}
    for name, (label, url) in resolved.items():
        payload = xlsx.get_xlsx(url)
        if payload is None:
            # HTTP 200 with an HTML body is CBSL's soft-404; treat as absent.
            print(f"  {name}: {url.split('/')[-1]} unavailable (soft-404)")
            continue
        payloads[name] = payload
        workbooks[name] = xlsx.load(payload)
        print(f"  {name}: {label} ({len(payload) // 1024} KB)")

    missing = [s.name for s in sources if s.required and s.name not in workbooks]
    if missing:
        age = vintage_age_days(doc_id)
        if age <= PUBLISH_GRACE_DAYS:
            print(
                f"{dataset}: vintage {doc_id} not fully published yet "
                f"({missing} soft-404, {age}d old); retrying next run"
            )
            store.regenerate_indexes(dataset)
            return 0
        raise ValueError(f"{dataset}: required workbooks unavailable: {missing}")

    try:
        payload = build(workbooks, doc_id)  # families that trim to their vintage
    except TypeError:
        payload = build(workbooks)
    clean = {"vintage": doc_id, **payload}
    blob = b"".join(payloads[name] for name in sorted(payloads))
    doc = Doc(dataset, doc_id, date, listing_url, Doc.sha256_of(blob))
    store.write_doc(doc, blob, "workbooks.bin", clean)
    store.regenerate_indexes(dataset)
    print(f"{dataset}: stored {doc_id}")
    return 1
