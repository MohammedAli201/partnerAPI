"""Keyboard and real localhost preview API checks in a fresh headless browser."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--chromium', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / '.simulation-runs/hubaal-react-preview'
    output.mkdir(parents=True, exist_ok=True)
    report = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(executable_path=args.chromium, headless=True)
        for width, scale in [(390, 1), (1440, 1), (720, 2)]:
            context = browser.new_context(viewport={'width': width, 'height': 1000}, device_scale_factor=scale, reduced_motion='reduce')
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            checks = []
            page.goto('http://127.0.0.1:8000/partners#enquiry')
            page.wait_for_selector('#root main h1')
            page.evaluate('document.fonts.ready')
            assert page.locator('#enquiry').bounding_box()['y'] >= 70
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            checks.append('anchor navigation and responsive reflow')
            if page.locator('#menu-toggle').is_visible():
                page.locator('#menu-toggle').click()
                expect(page.locator('#menu-close')).to_be_focused()
                page.keyboard.press('Shift+Tab')
                expect(page.locator('#mobile-menu > a')).to_be_focused()
                page.keyboard.press('Tab')
                expect(page.locator('#menu-close')).to_be_focused()
                page.keyboard.press('Escape')
                expect(page.locator('#menu-toggle')).to_be_focused()
                assert page.evaluate('getComputedStyle(document.body).overflow !== "hidden"')
                checks.append('native keyboard drawer trapping, Escape and scroll unlock')
            page.locator('#language').select_option('so')
            expect(page.locator('html')).to_have_attribute('lang', 'so')
            assert '?lang=so#enquiry' in page.url
            page.locator('#language').select_option('en')
            expect(page.locator('html')).to_have_attribute('lang', 'en')
            checks.append('language navigation preserves page and anchor')
            form = page.locator('#partner-enquiry')
            submit = form.locator('[type=submit]')
            submit.click()
            expect(form.locator('[name=company]')).to_be_focused()
            fields = {'company': 'Example <company>', 'name': 'Example Contact', 'email': 'contact@example.test',
                      'website': 'https://example.test', 'countries': 'Somalia',
                      'message': 'Synthetic preview used to verify the enquiry interface.'}
            for name, value in fields.items():
                form.locator('[name='+name+']').fill(value)
            form.locator('[name=volume]').select_option('1000_10000')
            form.locator('[value=mobile_wallet]').check()
            with page.expect_response('**/api/public/enquiries/preview') as response:
                submit.click()
            payload = response.value.json()
            assert payload['sent'] is False and payload['stored'] is False
            assert response.value.headers['cache-control'] == 'no-store'
            expect(page.locator('#draft-dialog')).to_be_visible()
            expect(page.locator('#edit-draft')).to_be_focused()
            expect(page.locator('#draft-summary')).to_contain_text('Example <company>')
            with page.expect_download() as download:
                page.locator('#download-draft').click()
            assert download.value.suggested_filename == 'hubaal-enquiry-preview.txt'
            assert 'not a submission confirmation' in Path(download.value.path()).read_text(encoding='utf-8')
            page.keyboard.press('Escape')
            expect(submit).to_be_focused()
            checks.append('real validated unsent/unstored API, escaped review, download and focus restoration')
            page.route('**/api/public/enquiries/preview', lambda route: route.fulfill(
                status=503, content_type='application/json', body='{"detail":"Unavailable"}'))
            submit.click()
            expect(form.locator('.form-status')).to_contain_text('has not been sent')
            expect(form.locator('[name=company]')).to_have_value(fields['company'])
            expect(submit).to_be_enabled()
            checks.append('injected 503 retains editable draft and reports failure')
            page.goto('http://127.0.0.1:8000/track')
            page.locator('#scenario').select_option('action')
            expect(page.locator('.tracking-title')).to_have_text('Action required')
            expect(page.locator('.status-timeline')).not_to_contain_text('Delivered')
            checks.append('real UNKNOWN example requires action')
            page.screenshot(path=str(output/f'track-browser-{width}-{scale}x.png'))
            page.goto('http://127.0.0.1:8000/help')
            page.locator('#help-search').fill('fee')
            assert page.locator('.faq-item:visible').count() > 0
            page.locator('.faq-item:visible summary').first.focus()
            page.keyboard.press('Enter')
            assert page.locator('.faq-item[open]').count() == 1
            page.locator('#help-search').fill('no matching question xyz')
            expect(page.locator('#no-results')).to_be_visible()
            checks.append('native keyboard FAQ and searchable empty state')
            page.goto('http://127.0.0.1:8000/')
            page.wait_for_selector('#root main h1')
            page.evaluate('document.fonts.ready')
            expect(page.locator('[data-testid=hero-title]')).to_contain_text('Your local payout')
            page.wait_for_function("[...document.querySelectorAll('#top img')].every(image => image.complete && image.naturalWidth > 0)")
            page.wait_for_timeout(1200)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            page.screenshot(path=str(output/f'home-browser-{width}-{scale}x.png'))
            page.evaluate('document.activeElement.blur()')
            page.locator('header').evaluate("header => header.style.position = 'static'")
            for selector, name in [('[data-testid=collage-bento]','collage'),('#how-it-works','how'),('#services','receiving'),('#why-us','clarity'),('#coverage','coverage'),('#integration','partner-band'),('#about','story'),('#onboarding','onboarding'),('#partner-form','enquiry'),('footer','footer')]:
                page.locator(selector).first.screenshot(path=str(output/f'{name}-{width}-{scale}x.png'))
            page.locator('[data-testid=hero-transact-cta]').click()
            assert '#partner-form' in page.url
            assert page.locator('#partner-form').bounding_box()['y'] >= 70
            checks.append('supplied home layout, local hero photo and partnership anchor')
            assert not errors, errors
            report.append({'width_css_px':width,'device_scale':scale,'passed':True,'checks':checks,'page_errors':errors})
            context.close()
        browser.close()
    (root/'docs/hubaal-react-interactions.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Three real-browser journeys passed, including 720 CSS px at 2x density (200% reflow equivalent).')


if __name__ == '__main__':
    main()
