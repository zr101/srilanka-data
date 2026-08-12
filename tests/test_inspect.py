import io
import json
from pathlib import Path

import pytest

from inspect_corpus import collect_numbers, normalize_haystack, value_found
from pipeline.doc import Doc
from pipeline.inspect import inspect_pdf
from pipeline.store import Store
from pipeline.validate import validate

FIXTURES = Path(__file__).parent / "fixtures"


def _image_only_pdf() -> bytes:
    """A one-page PDF whose only content is a raster image (no text layer)."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (600, 800), "white")
    draw = ImageDraw.Draw(img)
    for y in range(100, 700, 40):
        draw.line([(50, y), (550, y)], fill="black", width=3)
    buf = io.BytesIO()
    img.save(buf, format="PDF")
    return buf.getvalue()


# --- pipeline.inspect wrapper -------------------------------------------


def test_inspect_pdf_text_based_fixture():
    pytest.importorskip("pdf_inspector")
    # cbsl_daily fixtures are full untrimmed documents; edb_* fixtures are
    # blank-in-place trimmed and would classify against mostly-blank pages.
    record = inspect_pdf((FIXTURES / "cbsl_daily_20260805.pdf").read_bytes())
    assert record["pdf_type"] == "text_based"
    assert record["page_count"] >= 1
    assert set(record) == {
        "pdf_type",
        "confidence",
        "page_count",
        "pages_needing_ocr",
        "has_encoding_issues",
        "is_complex_layout",
        "pages_with_tables",
    }
    json.dumps(record)  # must be JSON-serializable as stored in clean.json


def test_inspect_pdf_returns_none_without_wheel(monkeypatch):
    monkeypatch.setattr("pipeline.inspect.pdf_inspector", None)
    assert inspect_pdf(b"%PDF-1.4 whatever") is None


def test_inspect_pdf_garbage_must_not_raise():
    result = inspect_pdf(b"%PDF-1.4 not really a report")
    assert result is None or isinstance(result, dict)


def test_image_only_pdf_classified_for_triage():
    pytest.importorskip("pdf_inspector")
    record = inspect_pdf(_image_only_pdf())
    assert record["pdf_type"] in ("scanned", "image_based")


# --- triage gate in validate() ------------------------------------------


def test_triage_gate_fires():
    # tbill_auctions has no registered checker, isolating the gate itself
    clean = {"_meta": {"inspection": {"pdf_type": "image_based", "confidence": 0.9}}}
    errors = validate("tbill_auctions", clean)
    assert errors and "image_based" in errors[0]


def test_triage_gate_noop_for_text_based_and_missing_meta():
    clean = {"_meta": {"inspection": {"pdf_type": "text_based", "confidence": 1.0}}}
    assert validate("tbill_auctions", clean) == []
    assert validate("tbill_auctions", {}) == []  # rebuild path: no _meta stamped
    low_conf = {"_meta": {"inspection": {"pdf_type": "scanned", "confidence": 0.5}}}
    assert validate("tbill_auctions", low_conf) == []


def test_triage_ignores_non_pdf_datasets():
    clean = {"_meta": {"inspection": {"pdf_type": "image_based", "confidence": 0.9}}}
    assert validate("nmra_registrations", clean) == []


# --- write_doc stamping + quarantine end-to-end --------------------------


def test_write_doc_stamps_and_quarantines(tmp_path):
    pytest.importorskip("pdf_inspector")
    store = Store(data_root=tmp_path)

    image_pdf = _image_only_pdf()
    doc = Doc("tbill_auctions", "img-doc", "2026-08-12", "http://x", Doc.sha256_of(image_pdf))
    with pytest.raises(ValueError, match="quarantined"):
        store.write_doc(doc, image_pdf, "original.pdf", {"date": "2026-08-12"})
    assert (tmp_path / "quarantine" / "tbill_auctions" / "img-doc" / "errors.json").exists()

    text_pdf = (FIXTURES / "cbsl_daily_20260805.pdf").read_bytes()
    doc = Doc("tbill_auctions", "txt-doc", "2026-08-12", "http://x", Doc.sha256_of(text_pdf))
    written = store.write_doc(doc, text_pdf, "original.pdf", {"date": "2026-08-12"})
    clean = json.loads((written / "clean.json").read_text())
    assert clean["_meta"]["inspection"]["pdf_type"] == "text_based"


# --- audit helpers (no wheel needed) --------------------------------------


def test_collect_numbers_paths():
    clean = {
        "fx": {"usd": {"sell": 340.1378}},
        "rows": [{"v": 10}, {"v": 20.5}],
        "flag": True,
        "_meta": {"inspection": {"confidence": 1.0}},
        "name": "text",
    }
    pairs = dict(collect_numbers(clean))
    assert pairs == {"fx.usd.sell": 340.1378, "rows.0.v": 10.0, "rows.1.v": 20.5}


def test_value_found_variants():
    hay = normalize_haystack("Deficit (1,234.5) then 10.20 and rate 9.77% total 4,150")
    assert value_found(hay, -1234.5)
    assert value_found(hay, 10.2)  # printed with a trailing zero
    assert value_found(hay, 9.77)
    assert value_found(hay, 4150)  # comma-separated in print
    assert not value_found(hay, 9.7)  # must not match inside 9.77
    assert not value_found(hay, 10.25)


def test_recall_on_cbsl_daily_fixture():
    pdf_inspector = pytest.importorskip("pdf_inspector")
    from datasets.cbsl_daily.parser import parse_pdf

    payload = (FIXTURES / "cbsl_daily_20260805.pdf").read_bytes()
    clean = parse_pdf(payload)
    pages = pdf_inspector.extract_pages_markdown_bytes(payload).pages
    haystack = normalize_haystack("\n".join(p.markdown for p in pages))
    numbers = collect_numbers(clean)
    found = sum(1 for _, v in numbers if value_found(haystack, v))
    assert numbers and found / len(numbers) >= 0.5
