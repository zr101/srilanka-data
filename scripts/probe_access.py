"""Compare ordinary HTTP clients from the actual collection runner."""
import subprocess
import requests

URLS = [
    'https://cbsl.gov.lk/en/statistics/economic-indicators',
    'https://www.cbsl.gov.lk/en/statistics/statistical-tables/financial-sector',
    'https://www.cbsl.gov.lk/sites/default/files/daily_economic_indicators_20261106_e.pdf',
]
for url in URLS:
    for ua in ('srilanka-data (open-source dataset; github.com/zr101/srilanka-data)', 'curl/8.7.1'):
        try:
            r = requests.get(url, headers={'User-Agent': ua}, timeout=25)
            print('requests', ua, r.status_code, r.headers.get('content-type'), len(r.content), r.content[:80], flush=True)
        except requests.RequestException as e:
            print(type(e).__name__, str(e), flush=True)
    r = subprocess.run(['curl', '-L', '--max-time', '30', '-sS', '-o', '/tmp/probe-body', '-w', '%{http_code} %{content_type} %{size_download}', url], capture_output=True, text=True)
    print('curl', r.returncode, r.stdout, r.stderr, flush=True)
