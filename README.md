# srilanka-data

Machine-readable datasets extracted from Sri Lankan government PDF/XLS publications, updated by scheduled scrapers (pattern inspired by [nuuuwan](https://github.com/nuuuwan)'s Lanka datasets).

Each dataset lives on its own `data_<dataset>` branch: per-doc dirs (`original.pdf` + `doc.json` + `clean.json`), regenerated indexes (`docs_all.tsv`, `docs_last100.tsv`, `summary.json`), and a `latest.json` pointer. Parsers are fixture-tested; raw originals are kept so clean data can be rebuilt retroactively (`rebuild.py`). `inspect_corpus.py` audits stored PDFs with [pdf-inspector](https://github.com/firecrawl/pdf-inspector) (classification, second-engine value recall); the same classifier quarantines scanned/image-only editions at ingest.

| Dataset | Source | Cadence |
|---|---|---|
| cbsl_daily | CBSL Daily Economic Indicators PDF | daily (working days) |
| tbill_auctions | Treasury auction result press releases | ~weekly |
| wer | Epidemiology Unit Weekly Epidemiological Report | weekly |
| sltda_arrivals | SLTDA weekly tourist arrivals reports | weekly |
| nmra_registrations | NMRA valid medicine registrations XLS | ~weekly |

Consumed by [srilanka-monitor](https://github.com/zr101/srilanka-monitor). MIT (code); data belongs to the respective government publishers, mirrored here with attribution.

## Scheduled updates and failures

GitHub Actions checks each dataset at 05:30 and 11:30 UTC daily (11:00 and 17:00
in Sri Lanka). Runs are serialized per dataset. Parser tests use locked Python
dependencies before collection; Ubuntu and the Node.js 24 action versions are
explicit. `PYTHONPATH=src:. python -m pipeline.status <dataset>` records the
publication/reference date, check time, last successful check, and updated,
unchanged, overdue, or error outcome in `status.json`. Publication age is evaluated
against the source's cadence, not the timestamp of regenerated indexes.

Failed scrapes preserve existing validated snapshots, publish their status, and
fail the job. Repeated identical failures reuse the existing issue without
posting daily comments. Git publication uses normal fast-forward pushes and
aborts on a rebase conflict. Each job summary includes its publication date and
failure reason. The optional access-probe workflow diagnoses public HTTP access
from a standard GitHub runner; a completed probe is not a healthy ingestion run.

Known external limitation verified November 8, 2026: CBSL returns HTTP 403 to
both tested GitHub-hosted Linux runner architectures, with Python and curl.
These jobs remain visibly failed until source access is restored. No alternate
host, paid proxy, or fabricated data is used to turn them green.
