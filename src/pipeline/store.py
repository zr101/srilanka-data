import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .doc import Doc
from .inspect import inspect_pdf
from .validate import validate

REPO_ROOT = Path(__file__).resolve().parents[2]

# Data lives in a sibling checkout of the dataset's data branch (nuuuwan's
# pattern): locally ../srilanka-data_data, in CI an actions/checkout of
# data_<dataset> into that path.
DEFAULT_DATA_ROOT = REPO_ROOT.parent / "srilanka-data_data"


class Store:
    def __init__(self, data_root: Path | None = None):
        env_root = os.environ.get("DATA_ROOT")
        self.root = Path(env_root) if env_root else (data_root or DEFAULT_DATA_ROOT)

    def dataset_dir(self, dataset: str) -> Path:
        return self.root / "data" / dataset

    def doc_dir(self, doc: Doc) -> Path:
        return self.dataset_dir(doc.dataset) / doc.date[:4] / doc.doc_id

    def exists(self, doc: Doc) -> bool:
        return (self.doc_dir(doc) / "doc.json").exists()

    def write_doc(self, doc: Doc, original: bytes, original_name: str, clean: dict) -> Path:
        """Layered write: raw payload + doc.json metadata + clean parsed data.
        Validation failures quarantine the doc (never published to latest.json)
        and raise, which fails the CI job → the failure-alert issue fires."""
        if original[:4] == b"%PDF":
            record = inspect_pdf(original)
            if record is not None:
                clean.setdefault("_meta", {})["inspection"] = record
        errors = validate(doc.dataset, clean)
        if errors:
            q = self.root / "quarantine" / doc.dataset / doc.doc_id
            q.mkdir(parents=True, exist_ok=True)
            (q / original_name).write_bytes(original)
            (q / "clean.json").write_text(json.dumps(clean, indent=2, ensure_ascii=False))
            (q / "errors.json").write_text(json.dumps(errors, indent=2))
            raise ValueError(f"{doc.dataset}/{doc.doc_id} quarantined: {errors}")
        d = self.doc_dir(doc)
        d.mkdir(parents=True, exist_ok=True)
        (d / original_name).write_bytes(original)
        (d / "clean.json").write_text(json.dumps(clean, indent=2, ensure_ascii=False))
        (d / "doc.json").write_text(doc.to_json())  # written last: presence = complete
        return d

    def regenerate_indexes(self, dataset: str) -> None:
        """Rebuild docs_all.tsv, docs_last100.tsv, summary.json, latest.json from disk."""
        base = self.dataset_dir(dataset)
        docs: list[tuple[Doc, Path]] = []
        for doc_json in sorted(base.rglob("doc.json")):
            docs.append((Doc.from_json(doc_json.read_text()), doc_json.parent))
        docs.sort(key=lambda pair: (pair[0].date, pair[0].doc_id), reverse=True)

        header = "doc_id\tdate\tsource_url\tsha256\n"
        rows = [f"{d.doc_id}\t{d.date}\t{d.source_url}\t{d.sha256}\n" for d, _ in docs]
        base.mkdir(parents=True, exist_ok=True)
        (base / "docs_all.tsv").write_text(header + "".join(rows))
        (base / "docs_last100.tsv").write_text(header + "".join(rows[:100]))

        latest_clean = None
        if docs:
            latest_clean = json.loads((docs[0][1] / "clean.json").read_text())
        (base / "latest.json").write_text(
            json.dumps(
                {
                    "dataset": dataset,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "doc_id": docs[0][0].doc_id if docs else None,
                    "date": docs[0][0].date if docs else None,
                    "data": latest_clean,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        # publish per-dataset metadata (backend documentation) alongside the data
        meta_src = REPO_ROOT / "datasets" / dataset / "meta.json"
        if meta_src.exists():
            meta = json.loads(meta_src.read_text())
            (base / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
            lines = [f"# {meta.get('title', dataset)}\n"]
            for key in ("source_url", "provider", "cadence", "parser_version"):
                if meta.get(key):
                    lines.append(f"- **{key}**: {meta[key]}")
            method = meta.get("method", {})
            if method:
                lines.append(f"- **method**: {method.get('technique', '')} ({method.get('library', '')})")
            for section in ("limitations", "fallback"):
                val = meta.get(section)
                if val:
                    lines.append(f"- **{section}**: {json.dumps(val, ensure_ascii=False)}")
            (base / "DATASET.md").write_text("\n".join(lines) + "\n")

        (base / "summary.json").write_text(
            json.dumps(
                {
                    "dataset": dataset,
                    "n_docs": len(docs),
                    "date_min": docs[-1][0].date if docs else None,
                    "date_max": docs[0][0].date if docs else None,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            )
        )
