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
