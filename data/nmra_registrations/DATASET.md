# NMRA valid medicine registrations

- **source_url**: https://www.nmra.gov.lk/
- **provider**: National Medicines Regulatory Authority
- **cadence**: ~weekly snapshot (date-stamped XLS)
- **parser_version**: 2
- **method**: typed cell read; xldate conversion; placeholder normalization (xlrd (BIFF8))
- **limitations**: ["snapshot of currently-valid list, not an event log", "14 duplicate REG.NO values upstream", "known upstream typos (schedule spellings, country aliases)"]
- **fallback**: {"plan_b": "previous snapshot (never fail on unchanged file)", "trigger": "homepage link missing"}
