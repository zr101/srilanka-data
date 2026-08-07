# CBSL Monetary — Interest Rates, Reserve Money, Monetary Survey

- **source_url**: https://www.cbsl.gov.lk/en/statistics/statistical-tables/monetary-sector
- **provider**: Central Bank of Sri Lanka
- **cadence**: monthly
- **parser_version**: 1
- **method**: listing-page discovery + header-text-anchored xlsx parse (openpyxl)
- **limitations**: ["OPR series starts 2024-11 when the single-policy-rate mechanism replaced SDFR/SLFR", "three different period encodings across the three workbooks"]
- **fallback**: {"plan_b": "cbsl_daily/cbsl_weekly PDF pipelines carry headline equivalents", "trigger": "listing page restructured or workbook link renamed"}
