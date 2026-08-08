# CBSL Activity — IIP, PMI, Business Sentiment

- **source_url**: https://www.cbsl.gov.lk/en/statistics/statistical-tables/real-sector/production-indicators
- **provider**: Central Bank of Sri Lanka
- **cadence**: monthly
- **parser_version**: 1
- **method**: listing-page discovery + header-text-anchored xlsx parse (openpyxl)
- **limitations**: ["IIP year headers are unreliable — the 2026-07 vintage labels its final two blocks both '2025'; years are derived from block position and disagreements reported in iip.notes", "BSI rows have an unlabelled companion row of negative figures whose meaning the workbook never states; those are not parsed", "housing table writes the year only on each year's Q1; it is carried forward"]
- **fallback**: {"plan_b": "cbsl_daily/cbsl_weekly PDF pipelines carry headline equivalents", "trigger": "listing page restructured or workbook link renamed"}
