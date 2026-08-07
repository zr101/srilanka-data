# PUCSL daily generation & reservoirs

- **source_url**: https://gendata.pucsl.gov.lk
- **provider**: PUCSL (regulator) Gen Data platform
- **cadence**: daily, ~1 day lag
- **parser_version**: 2
- **method**: plant->complex->energyType join for fuel attribution; single reportDate pinning (requests (JSON API))
- **limitations**: ["dispatch covers 38/40 plants (~1.7% delta)", "metadata contains duplicate ids and one XSS-probe name (sanitized)"]
- **fallback**: {"plan_b": "retry with backoff; no PDF fallback exists post-2025-03", "trigger": "API 5xx or empty day"}
