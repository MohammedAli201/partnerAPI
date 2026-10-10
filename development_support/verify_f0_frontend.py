"""Check the complete supplied f0 website and retained backend integration."""
from pathlib import Path
import argparse, json, re
from playwright.sync_api import sync_playwright, expect

BASE='http://127.0.0.1:8000'
ORDER=['top','stats-band','channels','why-hubaal','how-it-works','api','about','faq','partner-form']

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--chromium',required=True);parser.add_argument('--store-enquiries',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];out=root/'.simulation-runs/hubaal-copy-review';out.mkdir(exist_ok=True)
    report=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=args.chromium,headless=True)
        for width in [360,390,768,1024,1440]:
            context=browser.new_context(viewport={'width':width,'height':1000},reduced_motion='reduce')
            page=context.new_page();errors=[];failed=[];external=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('request',lambda r:external.append(r.url) if not r.url.startswith(BASE+'/') else None)
            page.on('response',lambda r:failed.append([r.url,r.status]) if r.status>=400 else None)
            page.goto(BASE+'/');page.wait_for_selector('h1');page.evaluate('document.fonts.ready')
            assert page.locator('main>section').evaluate_all('nodes=>nodes.map(n=>n.id||n.dataset.testid)')==ORDER
            title=page.locator('h1').evaluate('e=>{const s=getComputedStyle(e);return {size:parseFloat(s.fontSize),weight:s.fontWeight,family:s.fontFamily,color:s.color}}')
            assert title=={'size':68 if width>=1024 else 52 if width>=640 else 40,'weight':'800','family':'Manrope, sans-serif','color':'rgb(255, 255, 255)'},title
            assert page.locator('#top').evaluate('e=>getComputedStyle(e).backgroundColor')=='rgb(22, 32, 47)'
            assert page.locator('footer').evaluate('e=>getComputedStyle(e).backgroundColor')=='rgb(22, 32, 47)'
            assert page.locator('[data-testid=channels-grid] .payout-channel-group').count()==3
            expect(page.locator('#channels h2')).to_have_text('Three payout methods. One local partner.')
            expect(page.locator('#why-hubaal h2')).to_have_text('Local delivery. Clear payout outcomes.')
            assert page.locator('[data-testid=capabilities-grid]>div').count()==4
            assert page.locator('#why-hubaal .payout-capability-icon').count()==4
            assert page.locator('footer ul').nth(0).locator('a').count()==6
            assert page.locator('footer ul').nth(1).locator('a').count()==4
            expect(page.locator('[data-testid=approval-notice]')).to_contain_text('Hubaal is in the process of obtaining approval. Our payout service is not live yet.')
            expect(page.locator('[data-testid=api-example]')).to_contain_text('Illustrative data')
            expect(page.locator('[data-testid=api-example]')).to_contain_text('USD 100.00')
            expect(page.locator('footer')).to_contain_text('Hubaal. All rights reserved.')
            assert page.locator('[data-testid=partner-input-channels] option').all_text_contents()==['All channels','Wallets only','Banks only','Cash pickup only','Wallets + banks','Wallets + banks + cash pickup']
            for removed in ['payout-model','coverage-header','about-service-points','footer-cta']:
                assert page.locator('[data-testid='+removed+']').count()==0
            expect(page.locator('h1')).to_have_text('Your payout partner in Somalia.')
            expect(page.locator('[data-testid=hero-service-status]')).to_have_text('Partnership enquiries are open. Payout services are not yet live.')
            assert page.locator('.stats-marquee-set[aria-hidden=false] .stats-marquee-item>span:first-child').all_text_contents()==['USD payouts','Mobile wallets','Bank accounts','Cash pickup','Based in Mogadishu']
            expect(page.locator('[data-testid=api-example]')).to_contain_text('HB-EXAMPLE-001')
            expect(page.locator('[data-testid=api-example]')).to_contain_text('Instruction accepted. Payout pending.')
            expect(page.locator('[data-testid=stats-band]')).not_to_contain_text('1-day')
            assert page.locator('[data-testid=stats-band]>div').evaluate('e=>getComputedStyle(e).animationName')=='none'
            faq_style=page.locator('#faq-title').evaluate('e=>{let s=getComputedStyle(e);return {family:s.fontFamily,weight:s.fontWeight,leading:parseFloat(s.lineHeight)/parseFloat(s.fontSize)}}')
            assert faq_style['family']=='Manrope, sans-serif' and faq_style['weight']=='800' and abs(faq_style['leading']-1.2)<0.001,faq_style
            for selector,mobile,tablet,desktop in [('#channels h2',28,38,44),('#why-hubaal h2',32,40,48),('#how-it-works h2',28,38,44),('#api h2',32,44,52),('#about h2',32,40,52),('#faq h2',32,40,48),('#partner-form h2',28,38,44)]:
                computed=page.locator(selector).evaluate('e=>{let s=getComputedStyle(e);return {size:parseFloat(s.fontSize),family:s.fontFamily}}')
                assert computed=={'size':desktop if width>=1024 else tablet if width>=640 else mobile,'family':'Manrope, sans-serif'},(selector,width,computed)
            for link in page.locator('a[href^="#"],a[href^="/#"]').all():
                target=link.get_attribute('href').split('#',1)[1]
                assert page.locator('[id="'+target+'"]').count()==1,(width,target)
            if width<1024:
                toggle=page.locator('[data-testid=nav-mobile-menu-toggle]');toggle.click()
                panel=page.locator('[data-testid=mobile-menu-panel]');expect(panel).to_be_visible()
                page.keyboard.press('Shift+Tab');expect(panel.locator('a').last).to_be_focused()
                page.keyboard.press('Tab');expect(toggle).to_be_focused()
                page.keyboard.press('Escape');expect(panel).not_to_be_visible();expect(toggle).to_have_attribute('aria-expanded','false')
                assert page.evaluate('!document.querySelector("main").inert&&getComputedStyle(document.body).overflow!=="hidden"')
            for i in range(1,4):
                step=page.locator('[data-testid=how-step-'+str(i)+']')
                if step.get_attribute('aria-expanded')=='true':step.click();expect(step).to_have_attribute('aria-expanded','false')
                step.click();expect(step).to_have_attribute('aria-expanded','true')
            expect(page.locator('#about-title')).to_have_text('Your local team in Mogadishu.')
            expect(page.locator('[data-testid=about-service-points]')).to_have_count(0)
            expect(page.locator('#about a[href="mailto:partners@hubaal.so"]')).to_have_count(1)
            for i in range(1,4):
                item=page.locator('[data-testid=faq-item-'+str(i)+']')
                if item.get_attribute('aria-expanded')=='true':item.click();expect(item).to_have_attribute('aria-expanded','false')
                item.click();expect(item).to_have_attribute('aria-expanded','true')
            page.locator('[data-testid=faq-item-2]').click();expect(page.locator('[data-testid=faq-list]')).not_to_contain_text('SAHAL')
            assert not re.search(r'\b(SAHAL|SOS)\b',page.locator('body').inner_text(),re.I)
            assert page.locator('#coverage').count()==0
            text=page.locator('body').inner_text()
            assert not re.search(r'one business day|zero pre.funding|99.99%|40\+|sub.second|Hubaal Express|Money Transfer',text,re.I),text
            expect(page.locator('#how-it-works img')).to_have_attribute('alt','Woman seated at a market stall')
            page.evaluate('document.activeElement.blur();window.scrollTo(0,0)');page.wait_for_timeout(600)
            page.screenshot(path=str(out/f'home-{width}.png'))
            for selector,name in [('#channels','channels'),('#why-hubaal','capabilities'),('#how-it-works','workflow'),('#api','api'),('#about','about'),('#faq','faq'),('#partner-form','form'),('footer','footer')]:
                page.locator(selector).evaluate('e=>e.scrollIntoView({block:"start"})');page.wait_for_timeout(850)
                page.screenshot(path=str(out/f'{name}-{width}.png'))
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(width,name)
            assert page.locator('main img').count()==6
            assert page.locator('[data-channel-logo]').count()==5
            assert page.locator('main img').evaluate_all('nodes=>nodes.every(e=>e.complete&&e.naturalWidth>0)')
            assert not errors and not failed and not external,(errors,failed,external)
            report.append({'width':width,'all_sections_footer_and_interactions':'passed','hero':title,'overflow':False,'browser_errors':errors,'failed_requests':failed,'external_requests':external})
            context.close()

        page=browser.new_page(viewport={'width':390,'height':1000},reduced_motion='reduce')
        for route in ['/receive','/partners','/about','/help','/contact','/track','/privacy','/terms','/complaints','/partners/integration']:
            assert page.goto(BASE+route).status==200;page.wait_for_selector('main h1');page.evaluate('document.fonts.ready')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),route
            expect(page.locator('[data-testid=approval-notice]')).to_contain_text('not live yet')
            if route not in ['/privacy','/terms']:
                assert page.locator('header nav a').first.get_attribute('href')=='/#channels'
                assert page.locator('header nav a').first.evaluate('e=>getComputedStyle(e).color')=='rgb(88, 96, 107)'
        page.close()

        for width in [390,1440]:
            context=browser.new_context(viewport={'width':width,'height':1000},reduced_motion='reduce');page=context.new_page()
            page.goto(BASE+'/#partner-form');page.wait_for_selector('[data-testid=partner-form-element]')
            values={'company':f'Synthetic f0 browser review {width}','country':'Somalia','contact':'Synthetic Reviewer','email':'review@example.test'}
            for field,value in values.items():page.locator('[data-testid=partner-input-'+field+']').fill(value)
            page.locator('[data-testid=partner-input-channels]').select_option('Wallets + banks + cash pickup')
            page.route('**/api/partnerships',lambda route:route.fulfill(status=503,content_type='application/json',body='{"detail":"Injected review failure"}'))
            page.locator('[data-testid=partner-submit-btn]').click();expect(page.locator('[data-testid=partner-error-message]')).to_be_visible()
            expect(page.locator('[data-testid=partner-input-company]')).to_have_value(values['company'])
            page.unroute('**/api/partnerships')
            if not args.store_enquiries:page.route('**/api/partnerships',lambda route:route.fulfill(status=201,content_type='application/json',body=json.dumps({'received':True,'reference':f'ENQ-F0-REVIEW-{width}'})))
            with page.expect_response('**/api/partnerships') as response:page.locator('[data-testid=partner-submit-btn]').click()
            assert response.value.status==201,response.value.text()
            reference=response.value.json()['reference'];expect(page.locator('[data-testid=partner-success-message]')).to_contain_text(reference)
            expect(page.locator('[data-testid=partner-success-message]')).to_be_focused();page.wait_for_timeout(700)
            page.screenshot(path=str(out/f'enquiry-received-{width}.png'))
            page.locator('[data-testid=partner-new-enquiry-btn]').click();expect(page.locator('[data-testid=partner-input-company]')).to_have_value('')
            report.append({'width':width,'enquiry_reference':reference,'failure_keeps_fields':True,'new_enquiry_resets_form':True,'stored':args.store_enquiries})
            context.close()
        if args.store_enquiries:
            page=browser.new_page();page.goto(BASE+'/login')
            page.locator('input[name=username]').fill('demo-admin');page.locator('input[name=password]').fill('LocalDemo2026!')
            page.locator('button[type=submit]').click();page.wait_for_url('**/admin');page.goto(BASE+'/admin/partnerships')
            for width in [390,1440]:expect(page.locator('body')).to_contain_text(f'Synthetic f0 browser review {width}')
            page.screenshot(path=str(out/'admin-enquiries.png'));page.close()

        page=browser.new_page(viewport={'width':390,'height':1000})
        page.goto(BASE+'/');page.wait_for_selector('h1');page.evaluate('document.fonts.ready')
        track=page.locator('.stats-marquee-track')
        assert track.evaluate('e=>getComputedStyle(e).animationName')=='marquee'
        assert track.evaluate('e=>getComputedStyle(e).animationDuration')=='50s'
        before=track.evaluate('e=>getComputedStyle(e).transform');page.wait_for_timeout(500)
        assert before!=track.evaluate('e=>getComputedStyle(e).transform')
        band=page.locator('[data-testid=stats-band]').bounding_box()
        page.mouse.move(band['x']+band['width']/2,band['y']+band['height']/2)
        assert track.evaluate('e=>getComputedStyle(e).animationPlayState')=='paused'
        page.locator('[data-testid=stats-band]').screenshot(path=str(out/'marquee-motion.png'))
        page.mouse.move(0,0)
        page.locator('[data-testid=nav-mobile-menu-toggle]').click();page.locator('[data-testid=mobile-menu-panel] a').first.click();page.wait_for_timeout(1800)
        assert page.url.endswith('#channels')
        assert abs(page.locator('#channels').evaluate('e=>e.getBoundingClientRect().top')-80)<3
        page.locator('footer').scroll_into_view_if_needed();page.wait_for_timeout(900)
        page.locator('footer a[href="/#api"]').click();page.wait_for_timeout(1800)
        assert page.url.endswith('#api');assert abs(page.locator('#api').evaluate('e=>e.getBoundingClientRect().top')-80)<3
        page.go_back();page.wait_for_timeout(1800);assert page.url.endswith('#channels')
        page.goto(BASE+'/#coverage');page.wait_for_selector('#channels');page.evaluate('document.fonts.ready');page.wait_for_timeout(800)
        assert abs(page.locator('#channels').evaluate('e=>e.getBoundingClientRect().top')-80)<3
        page.close();browser.close()
    (out/('report-stored.json' if args.store_enquiries else 'report.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Copy review: nine sections with slim supporting marquee, approval footer, responsive Manrope typography, three FAQs, onboarding accordions, keyboard menu, ten routes, legacy coverage links, hash/history and enquiry recovery passed at five widths. '+('Two real enquiries verified in the admin inbox.' if args.store_enquiries else 'Enquiry receipts mocked.'))

if __name__=='__main__':main()
