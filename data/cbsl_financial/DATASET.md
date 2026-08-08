# CBSL Financial — Banking Soundness Indicators

- **source_url**: https://www.cbsl.gov.lk/en/statistics/statistical-tables/financial-sector
- **provider**: Central Bank of Sri Lanka
- **cadence**: quarterly (published with ~3 quarters' lag)
- **parser_version**: 1
- **method**: listing-page discovery + year-over-quarter header parse across all five sheets (openpyxl)
- **limitations**: ["publishes ~3 quarters behind — 2025-Q3 was the latest as of the 2026-06 vintage", "CBSL renamed non-performing loans to 'Stage 3 Loans' under IFRS 9; both wordings are matched", "licensed commercial banks only; the finance-companies sector is a separate workbook, not yet ingested", "outlets is annual and district-keyed rather than the family's year-over-quarter layout; it has its own parser"]
- **fallback**: {"plan_b": "CBSL Financial Stability Review PDF", "trigger": "workbook link renamed"}
