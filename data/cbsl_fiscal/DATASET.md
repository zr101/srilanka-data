# CBSL Fiscal — Government Operations and Outstanding Debt

- **source_url**: https://www.cbsl.gov.lk/en/statistics/statistical-tables/fiscal-sector
- **provider**: Central Bank of Sri Lanka
- **cadence**: annual
- **parser_version**: 1
- **method**: listing-page discovery + header-text-anchored xlsx parse (openpyxl)
- **limitations**: ["annual only; in-year fiscal detail lives in the Ministry of Finance releases", "columns are emitted wholesale because the revenue block gains lines between vintages"]
- **fallback**: {"plan_b": "cbsl_daily/cbsl_weekly PDF pipelines carry headline equivalents", "trigger": "listing page restructured or workbook link renamed"}
