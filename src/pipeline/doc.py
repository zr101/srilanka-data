import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass
class Doc:
    dataset: str
    doc_id: str
    date: str  # YYYY-MM-DD
    source_url: str
    sha256: str

    @staticmethod
    def sha256_of(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Doc":
        raw = json.loads(text)
        return cls(**{k: raw[k] for k in ("dataset", "doc_id", "date", "source_url", "sha256")})
