# CBSL External — Reserves, BOP, Monthly Trade

- **source_url**: https://www.cbsl.gov.lk/en/statistics/statistical-tables/external-sector
- **provider**: Central Bank of Sri Lanka
- **cadence**: monthly + quarterly
- **parser_version**: 1
- **method**: listing-page discovery + header-text-anchored xlsx parse (openpyxl)
- **limitations**: ["trade history capped at 72 months and BOP at 24 quarters to bound latest.json", "trade period headers mix real date cells with text ('Jan-26 (b)') — both are parsed", "the reserve template sheet is renamed monthly ('RDT (June 2026)'), so as_of comes from the sheet name", "tourism/remittances year headers carry footnote markers on the in-progress year ('2026 (b)(c)') — matched on the leading year only"]
- **fallback**: {"plan_b": "cbsl_daily/cbsl_weekly PDF pipelines carry headline equivalents", "trigger": "listing page restructured or workbook link renamed"}
