# EDB Export Performance Indicators

- **source_url**: https://www.srilankabusiness.com/ebooks/export-performance-indicators-of-sri-lanka-YYYY.pdf
- **provider**: Export Development Board
- **cadence**: annual
- **parser_version**: 1
- **method**: totals-table page location + line regex; dynamic year-header detection (pypdf)
- **limitations**: ["2023 edition layout differs (iLovePDF re-save) - skipped", "deep tables (sector/country/product) extraction pending"]
- **fallback**: {"plan_b": "customs wp-json monthly; CBSL WEI trade tables", "trigger": "totals page not found"}
