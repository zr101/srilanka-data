"""Audit stored PDF originals (and optionally test fixtures) with pdf-inspector.
Usage: PYTHONPATH=src:. python inspect_corpus.py [dataset ...] [--fixtures] [--markdown-dir DIR] [--json PATH]

Per doc: classification (text_based/scanned/image_based/mixed, encoding flags),
table-page coverage vs the pages each parser consumes ("data left on the
table"), and value recall — every numeric leaf of clean.json searched in
pdf-inspector's independently extracted markdown. Recall is a report, never a
failure: derived values (sums, shares) are excluded via DERIVED_PATHS.
"""

import argparse
import json
import re
import sys
from fnmatch import fnmatch
from pathlib import Path

try:
    import pdf_inspector
except ImportError:
    pdf_inspector = None

from pipeline.inspect import inspect_pdf
from pipeline.store import Store

PDF_DATASETS = [
    "cbsl_daily",
    "cbsl_price_report",
    "cbsl_weekly",
    "wer",
    "edb_indicators",
    "tbill_auctions",
    "sltda_arrivals",
    "forbes_tea",
]

# 1-indexed pages each parser consumes; None = whole document / TOC-driven.
PAGES_CONSUMED = {
    "cbsl_daily": {1},
    "tbill_auctions": {1},
    "cbsl_price_report": {1, 2},
    "cbsl_weekly": {1, 2, 3},
    "wer": None,
    "sltda_arrivals": None,
    "forbes_tea": None,
    "edb_indicators": None,
}

# fnmatch patterns of clean.json paths whose values are derived (never printed
# in the PDF) — excluded from the recall denominator. Extend as misses are triaged.
DERIVED_PATHS = {
    "sltda_arrivals": ["daily_sum", "top_markets_month.*.share_pct"],
    "tbill_auctions": ["results.*.tenor_days", "phase"],  # ISIN→tenor map; "Phase I" prints as a numeral
    "forbes_tea": ["repaired_year_rows"],  # parser bookkeeping, not a document value
}

# fixture filename glob -> dataset (fixtures have no clean.json; parse live)
FIXTURE_MAP = {
    "cbsl_daily_*.pdf": "cbsl_daily",
    "price_report_*.pdf": "cbsl_price_report",
    "wei_*.pdf": "cbsl_weekly",
    "wer_*.pdf": "wer",
    "edb_*.pdf": "edb_indicators",
    "tbill_*.pdf": "tbill_auctions",
    "treasury_*.pdf": "tbill_auctions",
    "sltda_latest.pdf": "sltda_arrivals",
}

BLANK_FIXTURE_CAVEAT = (
    "note: edb_* fixtures are blank-in-place trimmed (tests/test_edb_indicators.py) — "
    "mixed/low-confidence classification on them is expected, not alarming."
)


def collect_numbers(clean, prefix=""):
    """Recursive walk yielding ("fx_tt.usd.tt_sell", 340.1378)-style pairs for
    int/float leaves; bools and the _meta subtree are skipped."""
    out = []
    if isinstance(clean, dict):
        for key, value in clean.items():
            if prefix == "" and key == "_meta":
                continue
            out += collect_numbers(value, f"{prefix}.{key}" if prefix else key)
    elif isinstance(clean, list):
        for i, value in enumerate(clean):
            out += collect_numbers(value, f"{prefix}.{i}")
    elif isinstance(clean, bool):
        pass
    elif isinstance(clean, (int, float)):
        out.append((prefix, float(clean)))
    return out


def normalize_haystack(text):
    """Strip thousand separators and turn accounting negatives into minus signs."""
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)
    return re.sub(r"\((\d[\d.,]*)\)", r"-\1", text)


def _needles(value):
    """Printed-form candidates for a numeric value: plain decimal plus
    trailing-zero variants ("10.2" is printed as 10.2, 10.20, ...)."""
    a = abs(value)
    plain = format(a, "f").rstrip("0").rstrip(".") or "0"
    needles = {plain}
    for n in range(0, 5):
        if round(a, n) == a:
            needles.add(f"{a:.{n}f}" if n else str(int(a)))
    return needles


def value_found(haystack, value):
    for needle in _needles(value):
        if re.search(rf"(?<![\d.]){re.escape(needle)}(?![\d])", haystack):
            return True
    return False


def _is_derived(dataset, path):
    return any(fnmatch(path, pat) for pat in DERIVED_PATHS.get(dataset, []))


def audit_doc(dataset, doc_id, payload, clean, markdown_dir=None):
    row = {"dataset": dataset, "doc_id": doc_id}
    row.update(inspect_pdf(payload) or {"pdf_type": "unreadable", "confidence": 0.0})

    try:
        pages = pdf_inspector.extract_pages_markdown_bytes(payload).pages
    except Exception as err:  # noqa: BLE001 — audit rows must survive bad docs
        row["error"] = f"{type(err).__name__}: {err}"
        return row
    # Pages where the second engine extracts nothing — on CBSL's z-order-
    # scrambled pages this is pdf-inspector going blind, not an empty page,
    # so recall misses on such docs indict the oracle, not the parser.
    row["md_empty_pages"] = sum(1 for p in pages if not p.markdown.strip())
    if markdown_dir:
        out = Path(markdown_dir) / dataset / doc_id
        out.mkdir(parents=True, exist_ok=True)
        for page in pages:  # PageMarkdown.page is 0-indexed
            (out / f"page_{page.page + 1:03d}.md").write_text(page.markdown)

    consumed = PAGES_CONSUMED.get(dataset)
    row["unconsumed_table_pages"] = (
        sorted(p for p in row.get("pages_with_tables", []) if p not in consumed) if consumed else []
    )

    if clean is not None:
        haystack = normalize_haystack("\n".join(p.markdown for p in pages))
        numbers = [(p, v) for p, v in collect_numbers(clean) if not _is_derived(dataset, p)]
        misses = [(p, v) for p, v in numbers if not value_found(haystack, v)]
        row["values_total"] = len(numbers)
        row["recall_pct"] = round(100 * (1 - len(misses) / len(numbers)), 1) if numbers else None
        row["misses"] = [{"path": p, "value": v} for p, v in misses]
    return row


def iter_store_docs(store, dataset):
    for doc_json in sorted(store.dataset_dir(dataset).rglob("doc.json")):
        doc_dir = doc_json.parent
        original = doc_dir / "original.pdf"
        clean_path = doc_dir / "clean.json"
        if original.exists():
            clean = json.loads(clean_path.read_text()) if clean_path.exists() else None
            yield doc_dir.name, original.read_bytes(), clean


def iter_fixture_docs(datasets):
    import importlib

    fixtures = Path(__file__).parent / "tests" / "fixtures"
    for pdf in sorted(fixtures.glob("*.pdf")):
        dataset = next((ds for pat, ds in FIXTURE_MAP.items() if fnmatch(pdf.name, pat)), None)
        if dataset is None or dataset not in datasets:
            continue
        payload = pdf.read_bytes()
        try:
            parser = importlib.import_module(f"datasets.{dataset}.parser")
            clean = parser.parse_pdf(payload)
            parse_error = None
        except Exception as err:  # noqa: BLE001 — a fixture the main entry point rejects still classifies
            clean, parse_error = None, f"{type(err).__name__}: {err}"
        yield dataset, pdf.name, payload, clean, parse_error


def _triaged(row):
    return row.get("pdf_type") in ("scanned", "image_based") and row.get("confidence", 0) >= 0.7


def print_report(rows):
    rows.sort(
        key=lambda r: (
            not _triaged(r),
            r["recall_pct"] if r.get("recall_pct") is not None else 101,
            -len(r.get("unconsumed_table_pages", [])),
        )
    )
    header = (
        f"{'dataset':<18} {'doc':<22} {'type':<11} {'conf':>5} {'pages':>5} {'mdempty':>7} "
        f"{'ocr':>4} {'enc':>4} {'tbl':>4} {'uncons':>7} {'vals':>6} {'recall':>7} {'miss':>5}"
    )
    print(header)
    print("-" * len(header))
    for r in rows:
        flags = "!" if _triaged(r) else ""
        recall = f"{r['recall_pct']:.1f}%" if r.get("recall_pct") is not None else "-"
        print(
            f"{r['dataset']:<18} {r['doc_id'][:22]:<22} {flags + r.get('pdf_type', '?'):<11} "
            f"{r.get('confidence', 0):>5.2f} {r.get('page_count', 0):>5} {r.get('md_empty_pages', 0):>7} "
            f"{len(r.get('pages_needing_ocr', [])):>4} {'y' if r.get('has_encoding_issues') else '-':>4} "
            f"{len(r.get('pages_with_tables', [])):>4} {len(r.get('unconsumed_table_pages', [])):>7} "
            f"{r.get('values_total', 0):>6} {recall:>7} {len(r.get('misses', [])):>5}"
        )
    for r in rows:
        for miss in r.get("misses", [])[:10]:
            print(f"  miss {r['dataset']}/{r['doc_id']}: {miss['path']} = {miss['value']:g}")
        if len(r.get("misses", [])) > 10:
            print(f"  ... {len(r['misses']) - 10} more misses in {r['dataset']}/{r['doc_id']}")
        if r.get("error"):
            print(f"  error {r['dataset']}/{r['doc_id']}: {r['error']}")
        if r.get("parse_error"):
            print(f"  parse_error {r['dataset']}/{r['doc_id']}: {r['parse_error']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("datasets", nargs="*", default=None)
    ap.add_argument("--fixtures", action="store_true", help="also audit tests/fixtures/*.pdf")
    ap.add_argument("--markdown-dir", default=None, help="dump per-page markdown here")
    ap.add_argument("--json", dest="json_path", default=None, help="write full rows as JSON")
    args = ap.parse_args()
    if pdf_inspector is None:
        print("pdf-inspector is not installed (pip install pdf-inspector)")
        sys.exit(2)

    datasets = args.datasets or PDF_DATASETS
    store = Store()
    rows = []
    for dataset in datasets:
        for doc_id, payload, clean in iter_store_docs(store, dataset):
            rows.append(audit_doc(dataset, doc_id, payload, clean, args.markdown_dir))
    if args.fixtures:
        for dataset, name, payload, clean, parse_error in iter_fixture_docs(set(datasets)):
            row = audit_doc(dataset, f"fixture:{name}", payload, clean, args.markdown_dir)
            row["fixture"] = True
            if parse_error:
                row["parse_error"] = parse_error
            rows.append(row)

    if not rows:
        print(f"no PDF docs found under {store.root} (set DATA_ROOT or pass --fixtures)")
        sys.exit(1)
    print_report(rows)
    if any(r.get("fixture") and r["dataset"] == "edb_indicators" for r in rows):
        print(f"\n{BLANK_FIXTURE_CAVEAT}")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(rows, indent=2))
        print(f"\nwrote {args.json_path}")


if __name__ == "__main__":
    main()
