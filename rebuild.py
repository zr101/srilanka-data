"""Re-derive clean.json for stored originals after a parser upgrade.
Usage: PYTHONPATH=src:. python rebuild.py <dataset> [--force]
A dataset participates by exposing parser.rebuild(payload: bytes, existing_clean: dict) -> dict.
"""

import importlib
import json
import sys

from pipeline.store import Store
from pipeline.validate import validate


def main() -> None:
    dataset = sys.argv[1]
    force = "--force" in sys.argv
    parser = importlib.import_module(f"datasets.{dataset}.parser")
    rebuild_fn = getattr(parser, "rebuild", None)
    if rebuild_fn is None:
        print(f"{dataset}: parser has no rebuild(); nothing to do")
        return
    store = Store()
    base = store.dataset_dir(dataset)
    changed = 0
    for doc_json in sorted(base.rglob("doc.json")):
        doc_dir = doc_json.parent
        originals = [p for p in doc_dir.iterdir() if p.name.startswith("original.")]
        clean_path = doc_dir / "clean.json"
        if not originals or (clean_path.exists() and not force):
            continue
        existing = json.loads(clean_path.read_text()) if clean_path.exists() else {}
        try:
            clean = rebuild_fn(originals[0].read_bytes(), existing)
        except Exception as err:  # noqa: BLE001 — per-doc resilience
            print(f"{doc_dir.name}: rebuild failed ({err})")
            continue
        errors = validate(dataset, clean)
        if errors:
            print(f"{doc_dir.name}: validation failed {errors}; keeping old clean.json")
            continue
        clean_path.write_text(json.dumps(clean, indent=2, ensure_ascii=False))
        changed += 1
    store.regenerate_indexes(dataset)
    print(f"{dataset}: rebuilt {changed} docs")


if __name__ == "__main__":
    main()
