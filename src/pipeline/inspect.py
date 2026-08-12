"""Optional PDF classification via pdf-inspector (Rust, cp38-abi3 wheel).
Returns None when the wheel is unavailable so ingestion never depends on it."""

try:
    import pdf_inspector
except ImportError:  # wheel unavailable on this platform/Python
    pdf_inspector = None


def inspect_pdf(payload: bytes) -> dict | None:
    """Compact JSON-serializable classification of a PDF payload.

    pages_needing_ocr / pages_with_tables are 1-indexed (detect_pdf_bytes
    convention; classify_pdf_bytes is 0-indexed — do not mix the two)."""
    if pdf_inspector is None:
        return None
    try:
        r = pdf_inspector.detect_pdf_bytes(payload)
    except Exception:  # malformed PDF: classification failure is not a parse failure
        return None
    return {
        "pdf_type": r.pdf_type,  # text_based | scanned | image_based | mixed
        "confidence": round(r.confidence, 3),
        "page_count": r.page_count,
        "pages_needing_ocr": list(r.pages_needing_ocr),
        "has_encoding_issues": r.has_encoding_issues,
        "is_complex_layout": r.is_complex_layout,
        "pages_with_tables": list(r.pages_with_tables),
    }
