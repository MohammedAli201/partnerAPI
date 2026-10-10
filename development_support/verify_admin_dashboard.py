"""Browser checks against a running demo; funding POSTs are always intercepted."""
import argparse
import json
from decimal import Decimal
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--chromium', required=True)
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / '.simulation-runs/hubaal-admin-review'
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chromium)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
        page = context.new_page()
        errors, writes = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        # Safety boundary: this verifier never posts financial data to the demo database.
        def funding(route):
            if route.request.method != 'POST':
                return route.continue_()
            writes.append({'body': route.request.post_data_json,
                           'csrf': bool(route.request.headers.get('x-csrf-token'))})
            route.fulfill(status=503 if len(writes) == 1 else 200, content_type='application/json',
                          body=json.dumps({'detail': 'Synthetic temporary failure'} if len(writes) == 1 else
                                          {'journal_id': 'synthetic-browser-review', 'duplicate': False}))
        context.route('**/admin/api/funds/deposit', funding)
        page.goto(args.base + '/login')
        page.locator('[name=username]').fill('demo-admin')
        page.locator('[name=password]').fill('LocalDemo2026!')
        page.locator('button[type=submit]').click()
        page.wait_for_url('**/admin')
        expect(page.locator('#connLabel')).to_have_text('Connected')
        assert page.evaluate("localStorage.getItem('admin_executor_token')") is None
        assert not any('fonts.google' in entry['name'] for entry in page.evaluate('performance.getEntriesByType("resource")'))
        assert page.evaluate('document.fonts.check("400 14px Manrope")')

        def get(path):
            response = context.request.get(args.base + path)
            assert response.status == 200, (path, response.status)
            return response.json()

        def view(name, target):
            page.evaluate('(name) => location.hash = "/" + name', name)
            expect(page.locator(target)).to_be_visible()
            expect(page.locator('#freshness')).to_contain_text('Updated', timeout=20000)
            expect(page.locator('#banner')).to_be_hidden()

        summary = get('/admin/api/summary')
        for status in ['received', 'processing', 'sent', 'failed']:
            expect(page.get_by_test_id('summary-' + status + '-count')).to_have_text(f"{summary['payouts'][status]:,}")
        view('transactions', '#txTable')
        expect(page.locator('#txTable tbody tr')).to_have_count(50)
        page.locator('#next').click()
        expect(page.locator('#pageInfo')).to_contain_text('Showing 51')
        row = get('/admin/api/payouts?limit=1')['items'][0]
        page.locator('#search').fill(row['partner_tx_id'])
        expect(page.locator('#txCount')).to_have_text('1 result')
        page.locator('#txTable button').filter(has_text='Details').first.click()
        expect(page.get_by_test_id('drawer-id')).to_contain_text(row['id'])
        expect(page.get_by_test_id('drawer-amount')).to_contain_text(f"USD {Decimal(row['amount']):,.2f}")
        detail = get('/admin/api/payouts/' + row['id'])
        assert 'events' in detail and 'request_payload' not in detail
        expect(page.get_by_test_id('drawer-attempts')).not_to_contain_text('[object Object]')
        page.screenshot(path=str(output / 'detail-desktop.png'))
        page.keyboard.press('Escape')
        page.locator('#search').fill('')
        page.locator('#status').select_option('UNKNOWN')
        expect(page.locator('#txCount')).to_have_text(f"{summary['payouts']['unknown']:,} results")
        assert all(item['status'] == 'UNKNOWN' for item in get('/admin/api/payouts?status=UNKNOWN&limit=50')['items'])
        page.locator('#status').select_option('')

        view('earnings', '#earningsCards')
        page.locator('#earningsActivity').select_option('simulation')
        page.locator('#earningsFilters button').click()
        expect(page.locator('#earningsScope')).to_contain_text('simulation')
        report = get('/admin/api/earnings?preset=month&currency=USD&activity=simulation')
        for key in ['gross', 'net', 'pending', 'reversals']:
            expect(page.get_by_test_id('earnings-' + key + '-amount')).to_have_text(f"USD {Decimal(report['summary'][key]):,.2f}")
        expect(page.locator('#feeTable tbody tr')).to_have_count(50)
        page.locator('#feeNext').click()
        expect(page.locator('#feePageInfo')).to_contain_text('Showing 51')
        page.locator('#feeTable button').filter(has_text='Ledger audit').first.click()
        expect(page.locator('#businessTitle')).to_have_text('Transaction fee audit')
        expect(page.locator('#businessBody')).to_contain_text('Lifetime net revenue')
        page.screenshot(path=str(output / 'fee-audit-desktop.png'))
        page.keyboard.press('Escape')
        with page.expect_download() as downloaded:
            page.locator('#earningsExport').click()
        download = downloaded.value
        assert download.failure() is None
        csv = Path(download.path()).read_text(encoding='utf-8-sig')
        assert len(csv.splitlines()) > 1 and 'payout_id' in csv.splitlines()[0]
        page.locator('#earningsPartners tbody button').first.click()
        expect(page.locator('#earningsPartner')).not_to_have_value('')
        expect(page.locator('#feePageInfo')).to_contain_text('Showing 1')
        page.locator('#earningsPartner').fill('')
        page.locator('#earningsFilters button').click()

        view('funds', '#fundsTable')
        funds = get('/admin/api/funds/partners?limit=50')
        partner = funds['partners'][0]
        expect(page.locator('#fundsTable')).to_contain_text(f"{partner['funding_currency']} {Decimal(partner['balance_total']):,.2f}")
        page.locator('#fundsTable button').filter(has_text='Funding history').first.click()
        expect(page.locator('#businessBody')).to_contain_text('Funding history records partner deposits')
        page.keyboard.press('Escape')
        page.locator('#fundsTable button').filter(has_text='Record deposit').first.click()
        page.locator('#deposit-amount').fill('123.45')
        page.locator('#deposit-reference').fill('BROWSER-REVIEW-DO-NOT-POST')
        page.locator('#deposit-evidence').fill('bank://synthetic-browser-review')
        page.get_by_test_id('deposit-submit').click()
        assert not writes
        expect(page.locator('#deposit-amount')).to_have_attribute('readonly', '')
        page.get_by_test_id('deposit-submit').click()
        expect(page.get_by_test_id('deposit-status')).to_contain_text('Keep the same funding reference')
        page.get_by_test_id('deposit-submit').click()
        expect(page.locator('#businessRoot')).to_be_hidden()
        assert len(writes) == 2 and writes[0] == writes[1]
        assert writes[0]['csrf'] and writes[0]['body']['amount'] == '123.45'
        assert get('/admin/api/funds/partners?limit=50')['partners'][0]['balance_total'] == partner['balance_total']
        page.locator('#fundsSearch').fill(partner['name'])
        page.locator('#fundsFilters button').click()
        expect(page.locator('#fundsPageInfo')).to_contain_text('of 1')
        page.locator('#fundsSearch').fill('')
        page.locator('#fundsFilters button').click()

        view('enquiries', '#enquiriesTable')
        enquiries = get('/admin/api/partnerships')
        if enquiries['items']:
            page.locator('#enquiriesSearch').fill(enquiries['items'][0]['reference'])
            expect(page.locator('#enquiriesPageInfo')).to_contain_text('of 1')
        page.locator('#enquiriesSearch').fill('')
        # Error recovery preserves the last successfully loaded data.
        page.route('**/admin/api/partnerships?*', lambda route: route.fulfill(status=503, json={'detail': 'Synthetic outage'}))
        page.locator('#refreshEnquiries').click()
        expect(page.locator('#banner')).to_be_visible()
        expect(page.locator('#freshness')).to_contain_text('Stale')
        page.unroute('**/admin/api/partnerships?*')
        page.locator('#bannerRetry').click()
        expect(page.locator('#banner')).to_be_hidden()

        for width in [1440, 1024, 768, 390, 360]:
            page.set_viewport_size({'width': width, 'height': 900})
            for name, target in [('overview', '#recentTable'), ('transactions', '#txTable'), ('queue', '#queueTable'),
                                 ('earnings', '#earningsCards'), ('funds', '#fundsTable'), ('enquiries', '#enquiriesTable')]:
                view(name, target)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, name)
                if width in [1440, 390]:
                    page.screenshot(path=str(output / f'{name}-{width}.png'))
                results.append(f'{name}@{width}')
            if width == 390:
                view('earnings', '#earningsCards')
                page.locator('#earningsActivity').select_option('simulation')
                page.locator('#earningsFilters button').click()
                expect(page.locator('#feeTable tbody tr')).to_have_count(50)
                page.locator('#feeTable button').filter(has_text='Ledger audit').first.click()
                expect(page.locator('#businessRoot')).to_be_visible()
                bounds = page.locator('#businessDialog').bounding_box()
                assert bounds['y'] >= 0 and bounds['y'] + bounds['height'] <= 900
                assert page.locator('#businessBody').evaluate('(el) => el.scrollHeight > el.clientHeight')
                page.locator('#businessBody').evaluate('(el) => el.scrollTop = el.scrollHeight')
                page.screenshot(path=str(output / 'fee-audit-mobile.png'))
                page.keyboard.press('Escape')
                page.locator('#menuBtn').click()
                expect(page.locator('#sidebar')).to_have_class('sidebar open')
                assert page.evaluate('document.querySelector(".main").inert')
                page.keyboard.press('Shift+Tab')
                assert page.evaluate('document.querySelector("#sidebar").contains(document.activeElement)')
                page.keyboard.press('Escape')
                expect(page.locator('#menuBtn')).to_be_focused()

        page.set_viewport_size({'width': 1440, 'height': 1000})
        view('enquiries', '#enquiriesTable')
        malicious = '<img src=x onerror=window.UNSAFE=1>'
        synthetic = {'items': [{**enquiries['items'][0], 'company_name': malicious}] if enquiries['items'] else [], 'limit': 50, 'offset': 0, 'total': 1}
        page.route('**/admin/api/partnerships?*', lambda route: route.fulfill(json=synthetic))
        page.locator('#refreshEnquiries').click()
        if synthetic['items']:
            expect(page.locator('#enquiriesTable')).to_contain_text(malicious)
            assert page.locator('#enquiriesTable img').count() == 0 and page.evaluate('window.UNSAFE') is None
        page.unroute('**/admin/api/partnerships?*')
        # A delayed response from the previous view must not restore data after expiry.
        delayed = []
        page.route('**/admin/api/funds/partners?*', lambda route: delayed.append(route))
        with page.expect_request('**/admin/api/funds/partners?*'):
            page.evaluate('location.hash = "/funds"')
        expect(page.locator('#pageTitle')).to_have_text('Partner funds')
        page.route('**/admin/api/partnerships?*', lambda route: route.fulfill(status=401, json={'detail': 'Expired session'}))
        page.evaluate('location.hash = "/enquiries"')
        expect(page.locator('#connectPrompt')).to_be_visible()
        expect(page.locator('#enquiriesTable')).to_be_hidden()
        assert malicious not in page.locator('#enquiriesTable').inner_text()
        assert delayed
        delayed[0].fulfill(json=funds)
        expect(page.locator('#fundsTable')).not_to_contain_text(partner['name'])
        page.unroute('**/admin/api/funds/partners?*')
        page.unroute('**/admin/api/partnerships?*')
        page.locator('#connectPromptBtn').click()
        expect(page.locator('#sessionSignIn')).to_be_visible()
        page.locator('#reconnectSession').click()
        expect(page.locator('#connRoot')).to_be_hidden()
        expect(page.locator('#enquiriesTable')).to_be_visible()
        page.locator('#openConnection').click()
        page.locator('#logoutSession').click()
        page.wait_for_url('**/login')
        assert context.request.get(args.base + '/admin/api/session').status == 401
        assert not errors, errors
        report = {'checks': results, 'browser_errors': errors, 'funding_posts': '2 intercepted; no funding writes',
                  'integration': ['session login/logout', 'transactions search/status/page/details', 'earnings/activity/audit/CSV',
                                  'partner scope', 'balances/history/deposit review and idempotent retry', 'enquiries/search',
                                  'stale/retry', 'safe text', 'session expiration', 'mobile focus and overflow']}
        (output / 'browser-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report))
        browser.close()


if __name__ == '__main__':
    main()
