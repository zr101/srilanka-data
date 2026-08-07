# Weekly Epidemiological Report

- **source_url**: https://www.epid.gov.lk/weekly-epidemiological-report/weekly-epidemiological-report
- **provider**: Epidemiology Unit, Ministry of Health
- **cadence**: weekly
- **parser_version**: 3
- **method**: row-major token consumption; 26 RDHS x 14 diseases; SRI LANKA total row used as checksum (pypdf token stream)
- **limitations**: ["disease list pinned to template order (verified by checksum)", "Kalmunai and Ampara share district LK-52 for geo joins - use rdhs key for sums", "p4 vaccine table not yet extracted"]
- **fallback**: {"plan_b": "previous week's issue; lk_dengue mirror for dengue", "trigger": "checksum failure or <20 rows"}
