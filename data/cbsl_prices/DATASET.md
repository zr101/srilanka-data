# CBSL Prices — CCPI/NCPI and Wage Rate Indices

- **source_url**: https://www.cbsl.gov.lk/en/statistics/statistical-tables/real-sector/prices-wages-employment
- **provider**: Central Bank of Sri Lanka
- **cadence**: monthly
- **parser_version**: 1
- **method**: listing-page discovery + header-text-anchored xlsx parse (openpyxl)
- **limitations**: ["CPI workbooks carry a rolling ~14-month window only; long Y-o-Y history comes from CBSL's inflation widget", "NCPI publishes about a month behind CCPI"]
- **fallback**: {"plan_b": "cbsl_daily/cbsl_weekly PDF pipelines carry headline equivalents", "trigger": "listing page restructured or workbook link renamed"}
