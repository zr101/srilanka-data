# CBSL Daily Economic Indicators

- **source_url**: https://www.cbsl.gov.lk/sites/default/files/daily_economic_indicators_YYYYMMDD_e.pdf
- **provider**: Central Bank of Sri Lanka
- **cadence**: daily (working days, ~17:00 Colombo)
- **parser_version**: 2
- **method**: coordinate-based extraction (text layer is z-order scrambled); per-panel crops with upright-char filtering (pdfplumber)
- **limitations**: ["subset of the ~14 panels extracted (full extraction in progress)", "no weekend editions"]
- **fallback**: {"plan_b": "next-day WEI tables; treasury phase-I WAYR (verified identical); lanka_data_timeseries mirror", "trigger": "URL 404 for >3 working days or parse failure"}
