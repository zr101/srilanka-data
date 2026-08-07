# CBSL Daily Price Report

- **source_url**: https://www.cbsl.gov.lk/sites/default/files/cbslweb_documents/statistics/pricerpt/price_report_YYYYMMDD_e.pdf
- **provider**: Central Bank of Sri Lanka
- **cadence**: daily (working days)
- **parser_version**: 1
- **method**: page 2 table by data-driven column clustering; page 1 highlights by bounded heading association (pdfplumber)
- **limitations**: ["period label is 'Yesterday' most days and 'Last Friday' on Mondays; compares_to records which, and the value columns are found from the data so the wording cannot break the parse", "some editions interleave two columns' characters into one unreadable line, destroying a commodity heading; orphaned highlight rows are dropped rather than misattributed and the count is reported in notes", "page-2 table is unaffected by that scrambling and parses in full every day", "fish and some staples appear in highlights but not in the page-2 table"]
- **fallback**: {"plan_b": "HARTI daily prices via nuuuwan/lk_food", "trigger": "PDF layout change"}
