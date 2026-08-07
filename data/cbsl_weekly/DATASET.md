# CBSL Weekly Economic Indicators

- **source_url**: https://www.cbsl.gov.lk/sites/default/files/cbslweb_documents/statistics/wei/WEI_YYYYMMDD_e.pdf
- **provider**: Central Bank of Sri Lanka
- **cadence**: weekly (Friday)
- **parser_version**: 2
- **method**: prose-highlights extraction; full-table extraction in progress (title-anchored pdfplumber crops) (pypdf + regex)
- **limitations**: ["mid-month editions lack reserves/trade prose (tables cover them — upgrade pending)", "provisional figures revised ±1%"]
- **fallback**: {"plan_b": "reserves from WEI table 4.3; customs wp-json for trade", "trigger": "prose patterns absent"}
