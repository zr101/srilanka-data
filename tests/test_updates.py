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
