# Treasury bill auction results

- **source_url**: https://www.treasury.gov.lk/web/result-treasury-bills
- **provider**: Ministry of Finance
- **cadence**: ~weekly (Wednesday auctions)
- **parser_version**: 1
- **method**: prose regex over phase-II releases; ISIN prefix → tenor (pypdf + regex)
- **limitations**: ["phase-I table variant not yet parsed", "buildId re-scraped per run (upstream deploys rotate it)"]
- **fallback**: {"plan_b": "CBSL auction pages; DEI primary yields", "trigger": "listing JSON shape change"}
