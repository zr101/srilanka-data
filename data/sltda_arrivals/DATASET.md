# SLTDA tourist arrivals

- **source_url**: https://www.sltda.gov.lk/en/weekly-tourist-arrivals-reports-YYYY
- **provider**: Sri Lanka Tourism Development Authority
- **cadence**: weekly reports, posted monthly-bundled
- **parser_version**: 2
- **method**: line regex (monthly + market tables); page-indexed disambiguation; daily series de-rotation pending (pdfplumber)
- **limitations**: ["monthly bundling lags up to 5 weeks", "2018 used as pre-pandemic reference column"]
- **fallback**: {"plan_b": "SLTDA monthly statistical bulletins (richer splits)", "trigger": "listing empty"}
