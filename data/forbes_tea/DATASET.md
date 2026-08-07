# Colombo tea auction quantities & averages (Forbes & Walker)

- **source_url**: https://www.forbestea.com/statistics-weekly-tea-auction-quantities-&-averages
- **provider**: Forbes & Walker Tea Brokers
- **cadence**: weekly (auction Tue/Wed)
- **parser_version**: 1
- **method**: line regex over the year table (sale date x elevation qty/avg) (pdfplumber)
- **limitations**: ["broker publication (authoritative in practice; Tea Board site lacks machine-readable stats)", "known upstream year typo repaired and counted"]
- **fallback**: {"plan_b": "John Keells tea market reports; Forbes 22-page weekly report tables", "trigger": "listing or PDF missing 2 consecutive weeks"}
