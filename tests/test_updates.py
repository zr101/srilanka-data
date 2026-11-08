from datetime import datetime, timezone
from unittest.mock import patch
import pytest
import requests
from pipeline.http import get, get_pdf
from pipeline.status import make_status
from datasets.nmra_registrations.scraper import discover_registration
from datasets.nmra_registrations.parser import parse_xls


def response(code, body=b''):
    result = requests.Response()
    result.status_code = code
    result._content = body
    result.url = 'https://example.com/report'
    return result


def test_nmra_current_link():
    html = '<a href="https://cdn.prod.website-files.com/List%20of%20Registered%20Drugs%20By%20brand-generic.xls%2002.11.2026.xls"><span>NMRA Registered Medicines</span></a>'
    url, date = discover_registration(html)
    assert date == '2026-11-02'
    assert url.endswith('02.11.2026.xls')


def test_nmra_picks_latest_and_resolves_relative_links():
    html = '<a href="/Valid_medicine_registrations_01.10.2026.xls">Valid medicines</a><a href="/drugs_02.11.2026.xlsx">Registered Medicines</a><a href="/prices_03.11.2026.xls">Maximum retail prices</a>'
    assert discover_registration(html) == ('https://www.nmra.gov.lk/drugs_02.11.2026.xlsx', '2026-11-02')


def test_nmra_no_matching_download():
    with pytest.raises(RuntimeError):
        discover_registration('<a href="/prices.xls">Prices</a>')


def test_xlsx_format_and_dates(tmp_path):
    import openpyxl
    workbook = openpyxl.Workbook()
    workbook.active.append(['GENERIC NAME', 'REG.DATE'])
    workbook.active.append(['Medicine', datetime(2026, 11, 2)])
    path = tmp_path / 'registrations.xls'
    workbook.save(path)
    assert parse_xls(str(path)) == (['GENERIC NAME', 'REG.DATE'], [['Medicine', '2026-11-02']])


@pytest.mark.parametrize('code', [401, 403])
def test_permanent_errors_do_not_retry(code):
    with patch('pipeline.http.requests.get', return_value=response(code)) as fetch, patch('pipeline.http.time.sleep') as sleep:
        with pytest.raises(RuntimeError, match=f'HTTP {code}'):
            get('https://example.com/report')
        assert fetch.call_count == 1
        sleep.assert_not_called()


@pytest.mark.parametrize('code', [429, 500, 503])
def test_transient_errors_retry(code):
    with patch('pipeline.http.requests.get', side_effect=[response(code), response(200, b'ok')]), patch('pipeline.http.time.sleep'):
        assert get('https://example.com/report').content == b'ok'


def test_missing_and_invalid_pdf():
    with patch('pipeline.http.requests.get', return_value=response(404)):
        assert get_pdf('https://example.com/report') is None
    with patch('pipeline.http.requests.get', return_value=response(200, b'<html>error</html>')):
        with pytest.raises(ValueError, match='not return a PDF'):
            get_pdf('https://example.com/report')


def test_old_snapshot_does_not_become_fresh_on_successful_check():
    snapshot = {'date': '2026-08-01', 'doc_id': 'old', 'data': {'v': 1}}
    status = make_status('cbsl_daily', {}, snapshot, snapshot, None, datetime(2026,11,8,tzinfo=timezone.utc))
    assert status['status'] == 'overdue'
    assert status['outcome'] == 'unchanged'
    assert status['publication_date'] == '2026-08-01'


def test_failed_check_preserves_last_success():
    status = make_status('cbsl_daily', {'last_successful_check_at': '2026-11-06'}, {}, {'date': '2026-11-06'}, 'HTTP 403', datetime(2026,11,8,tzinfo=timezone.utc))
    assert status['status'] == 'error'
    assert status['last_successful_check_at'] == '2026-11-06'


def test_monthly_publication_unchanged_is_success():
    snapshot = {'date': '2026-10-30', 'doc_id': 'october', 'data': {'v': 1}}
    status = make_status('cbsl_prices', {}, snapshot, snapshot, None, datetime(2026,11,8,tzinfo=timezone.utc))
    assert (status['status'], status['outcome']) == ('ok', 'unchanged')


def test_wer_uses_issue_date_not_download_day():
    from pathlib import Path
    from datasets.wer.parser import publication_date
    assert publication_date((Path(__file__).parent / 'fixtures/wer_53_26.pdf').read_bytes()) == '2026-06-28'


def test_wer_abbreviated_month():
    from datasets.wer.parser import publication_date
    class Page:
        def extract_text(self): return 'Vol. 53 No. 31 27th July – 02nd Aug 2026'
    with patch('datasets.wer.parser.PdfReader') as reader:
        reader.return_value.pages = [Page()]
        assert publication_date(b'fixture') == '2026-08-02'


def test_tourism_partial_month_includes_current_arrivals():
    from datasets.sltda_arrivals.parser import MONTH_ROW_RE
    match = MONTH_ROW_RE.match('November 195,582 212,906 28,633')
    assert match and match.group(4) == '28,633'
    assert not MONTH_ROW_RE.match('December 253,169 258,928')


def test_tourism_date_is_report_end_not_month_end():
    from datasets.sltda_arrivals.parser import reporting_date
    class Page:
        def extract_text(self): return 'Tourist arrivals from 01st to 5th November 2026'
    with patch('datasets.sltda_arrivals.parser.PdfReader') as reader:
        reader.return_value.pages = [Page()]
        assert reporting_date(b'fixture') == '2026-11-05'


def test_treasury_section_links_are_not_lost():
    from datasets.tbill_auctions.scraper import publication_links
    listing = {'pageProps': {'sections': [{'html': '<p>&gt; 05.11.2026 <a href="https://www.treasury.gov.lk/api/file/7dad9782-5291-4c43-954d-3c74434804c7">Press Release | English</a></p>'}], 'pageData': {'links': []}}}
    links = publication_links(listing)
    assert len(links) == 1
    assert links[0]['title'].startswith('05.11.2026')


def test_current_publication_fixtures():
    from pathlib import Path
    from datasets.tbill_auctions.parser import parse_pdf as treasury
    from datasets.sltda_arrivals.parser import parse_pdf as tourism, reporting_date
    fixtures = Path(__file__).parent / 'fixtures'
    assert treasury((fixtures / 'tbill_20261105.pdf').read_bytes())['results'] == [{'tenor_days': 364, 'way_pct': 9.95}]
    payload = (fixtures / 'sltda_20261105.pdf').read_bytes()
    assert reporting_date(payload) == '2026-11-05'
    assert tourism(payload)['ytd_total'] == 1890937
