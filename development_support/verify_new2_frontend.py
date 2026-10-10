"""Verify supplied new2 typography, complete footer, routes and real enquiry flow."""
from pathlib import Path
import argparse,json,re
from playwright.sync_api import sync_playwright,expect

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--chromium',required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    source=root/'.simulation-runs/hubaal-new2-source/src/components'
    out=root/'.simulation-runs/hubaal-new2-review';out.mkdir(exist_ok=True)
    report=[]
    components={'Hero':'#top','Channels':'#channels','HowItWorks':'#how-it-works','Partners':'#coverage',
        'PartnerBand':'#integration','About':'#about','PartnershipForm':'#partner-form','Footer':'footer'}
    props=['fontFamily','fontSize','fontWeight','lineHeight','letterSpacing','fontVariantNumeric','textTransform']
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=args.chromium,headless=True)
        for width in [360,390,768,1024,1440]:
            context=browser.new_context(viewport={'width':width,'height':1000},reduced_motion='reduce')
            page=context.new_page();errors=[];external=[];failed=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('request',lambda r:external.append(r.url) if not r.url.startswith('http://127.0.0.1:8000/') else None)
            page.on('response',lambda r:failed.append([r.url,r.status]) if r.status>=400 else None)
            page.goto('http://127.0.0.1:8000/');page.wait_for_selector('h1');page.evaluate('document.fonts.ready')
            assert page.locator('main>section').evaluate_all('nodes=>nodes.map(n=>n.id)')==['top','channels','how-it-works','coverage','integration','about','partner-form']
            assert page.locator('[data-testid=channels-grid]>div').count()==5
            assert page.locator('main img').count()==5
            assert page.locator('#top img').evaluate('e=>e.complete&&e.naturalWidth>0')
            expect(page.locator('#top img')).to_have_attribute('alt','Woman seated at a market stall')
            assert page.locator('#channels').evaluate('e=>parseFloat(getComputedStyle(e).paddingTop)')==(64 if width>=640 else 48)
            assert page.locator('[data-testid=partner-input-channels] option').all_text_contents()==['All channels','Wallets only','Banks only','Wallets + banks']
            metrics=[]
            for name,selector in components.items():
                for cls in dict.fromkeys(re.findall(r'className="([^"]*)"',(source/(name+'.jsx')).read_text(encoding='utf-8'))):
                    if not any(t.startswith(('font-','leading-','tracking-')) or re.match(r'(?:sm:|lg:)?text-(?:xs|sm|base|lg|xl|[2-6]xl|\[\d)',t) for t in cls.split()):continue
                    # Error/success panels are checked through the actual form below.
                    if name=='PartnershipForm' and cls in ['text-center py-10','mt-5 text-2xl font-bold text-ink-light','mt-3 text-base text-ink-dim max-w-xs mx-auto','font-mono text-sm text-gold','mt-7 text-sm font-semibold text-gold border border-gold/40 rounded-full px-6 py-2.5 hover:bg-gold/5 transition-colors','text-sm text-red-600']:continue
                    result=page.locator(selector).evaluate(r'''(section,{cls,props})=>{
                        const tokens=cls.split(/\s+/),element=[...section.querySelectorAll('[class]')].find(e=>e.classList.length===tokens.length&&tokens.every(t=>e.classList.contains(t)));
                        if(!element)return {missing:cls};
                        const probe=document.createElement(element.tagName);probe.className=cls;probe.textContent='Hubaal USD 100.00';probe.style.visibility='hidden';element.parentElement.append(probe);
                        const actual=getComputedStyle(element),expected=getComputedStyle(probe),changes={};
                        for(const key of props)if(actual[key]!==expected[key])changes[key]={actual:actual[key],expected:expected[key]};
                        const values=Object.fromEntries(props.map(k=>[k,actual[k]]));probe.remove();return {changes,values};
                    }''',{'cls':cls,'props':props})
                    assert not result.get('missing'),(name,width,result)
                    assert not result.get('changes'),(name,width,cls,result)
                    metrics.append({'component':name,'class':cls,**result['values']})
            size=page.locator('h1').evaluate('e=>parseFloat(getComputedStyle(e).fontSize)')
            assert size==(64 if width>=1024 else 52 if width>=640 else 38)
            assert page.locator('body').evaluate('e=>getComputedStyle(e).backgroundColor')=='rgb(255, 255, 255)'
            assert page.locator('body').evaluate('e=>getComputedStyle(e).fontFamily').startswith('Manrope')
            assert page.locator('footer').evaluate('e=>getComputedStyle(e).backgroundColor')=='rgb(22, 32, 47)'
            expect(page.locator('footer')).to_contain_text('Hubaal Money Transfer. All rights reserved.')
            expect(page.locator('footer')).to_contain_text('hello@hubaal.so')
            assert page.locator('footer [data-testid=nav-logo]').inner_text()=='HUBAAL\nMONEY TRANSFER'
            assert page.locator('footer ul').nth(0).locator('a').count()==5
            assert page.locator('footer ul').nth(1).locator('a').count()==4
            assert page.locator('footer a[href="mailto:hello@hubaal.so"]').count()==1
            assert page.locator('footer a[href="mailto:partners@hubaal.so"]').count()==1
            for selector,size,weight in [('[data-testid=partner-input-company]',16,'400'),('[data-testid=partner-submit-btn]',16,'600')]:
                value=page.locator(selector).evaluate('e=>({size:parseFloat(getComputedStyle(e).fontSize),weight:getComputedStyle(e).fontWeight})')
                assert value=={'size':size,'weight':weight},value
            if width<1024:
                toggle=page.locator('[data-testid=nav-mobile-menu-toggle]');toggle.click()
                panel=page.locator('[data-testid=mobile-menu-panel]');expect(panel).to_be_visible()
                page.keyboard.press('Shift+Tab');expect(panel.locator('a').last).to_be_focused()
                page.keyboard.press('Tab');expect(toggle).to_be_focused()
                page.keyboard.press('Escape');expect(panel).not_to_be_visible()
                expect(toggle).to_have_attribute('aria-expanded','false')
                assert page.evaluate('getComputedStyle(document.body).overflow!="hidden"&&!document.querySelector("main").inert')
            page.evaluate('document.activeElement.blur();window.scrollTo(0,0)')
            page.screenshot(path=str(out/f'home-{width}.png'))
            for selector,name in [('#channels','channels'),('#coverage','coverage'),('#partner-form','form'),('footer','footer')]:
                page.locator(selector).evaluate('e=>e.scrollIntoView({block:"start"})')
                page.wait_for_timeout(1000)  # Let the supplied intersection reveals finish before visual review.
                page.screenshot(path=str(out/f'{name}-{width}.png'))
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),width
            assert not errors and not external and not failed,(errors,external,failed)
            report.append({'width':width,'source_typography':metrics,'footer_and_structure':'passed'})
            context.close()

        # Original supplied legal pages and all retained public routes work.
        page=browser.new_page(viewport={'width':390,'height':1000},reduced_motion='reduce')
        for route in ['/receive','/partners','/about','/help','/contact','/track','/privacy','/terms','/complaints','/partners/integration']:
            response=page.goto('http://127.0.0.1:8000'+route);assert response.status==200
            page.wait_for_selector('main h1');page.evaluate('document.fonts.ready')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),route
            if route in ['/privacy','/terms']:
                assert page.locator('[data-testid=legal-title]').count()==1
                page.screenshot(path=str(out/('legal-'+route[1:]+'.png')))
            else:
                assert page.locator('header nav a').first.get_attribute('href')=='/#channels'
                assert page.locator('[data-testid=nav-transact-btn]').get_attribute('href')=='/#partner-form'
        page.close()

        # Supplied smooth scrolling also supports the complete footer and browser history.
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.goto('http://127.0.0.1:8000/');page.wait_for_selector('h1');page.evaluate('document.fonts.ready')
        page.locator('header nav a').first.click();page.wait_for_timeout(1700)
        assert page.url.endswith('#channels')
        assert abs(page.locator('#channels').evaluate('e=>e.getBoundingClientRect().top')-80)<3
        page.locator('footer').scroll_into_view_if_needed();page.wait_for_timeout(1000)
        page.locator('footer a[href="/#about"]').click();page.wait_for_timeout(1700)
        assert page.url.endswith('#about')
        assert abs(page.locator('#about').evaluate('e=>e.getBoundingClientRect().top')-80)<3
        page.go_back();page.wait_for_timeout(1700)
        assert page.url.endswith('#channels')
        page.close()

        # Real form storage on the local demo; no email delivery or payout creation.
        for width in [390,1440]:
            context=browser.new_context(viewport={'width':width,'height':1000},reduced_motion='reduce');page=context.new_page()
            page.goto('http://127.0.0.1:8000/#partner-form');page.wait_for_selector('[data-testid=partner-form-element]');page.evaluate('document.fonts.ready')
            values={'company':f'Synthetic new2 browser review {width}','country':'Somalia','contact':'Synthetic Reviewer','email':'review@example.test'}
            for field,value in values.items():page.locator('[data-testid=partner-input-'+field+']').fill(value)
            page.locator('[data-testid=partner-input-channels]').select_option('Wallets + banks')
            page.route('**/api/partnerships',lambda route:route.fulfill(status=503,content_type='application/json',body='{"detail":"Injected browser verification failure"}'))
            page.locator('[data-testid=partner-submit-btn]').click();expect(page.locator('[data-testid=partner-error-message]')).to_be_visible()
            expect(page.locator('[data-testid=partner-input-company]')).to_have_value(values['company'])
            page.unroute('**/api/partnerships')
            with page.expect_response('**/api/partnerships') as response:page.locator('[data-testid=partner-submit-btn]').click()
            assert response.value.status==201,response.value.text()
            reference=response.value.json()['reference'];expect(page.locator('[data-testid=partner-success-message]')).to_contain_text(reference)
            expect(page.locator('[data-testid=partner-success-message]')).to_be_focused()
            page.wait_for_timeout(1000)
            page.screenshot(path=str(out/f'enquiry-received-{width}.png'))
            report.append({'width':width,'real_enquiry_reference':reference,'failure_preserves_fields':True,'stored_receipt':True})
            context.close()
        # Administrator sees both real browser submissions in the dedicated inbox.
        page=browser.new_page();page.goto('http://127.0.0.1:8000/login')
        page.locator('input[name=username]').fill('demo-admin');page.locator('input[name=password]').fill('LocalDemo2026!')
        page.locator('button[type=submit]').click();page.wait_for_url('**/admin')
        page.goto('http://127.0.0.1:8000/admin/partnerships')
        expect(page.locator('body')).to_contain_text('Synthetic new2 browser review 390')
        expect(page.locator('body')).to_contain_text('Synthetic new2 browser review 1440')
        page.screenshot(path=str(out/'admin-enquiries.png'));page.close()
        browser.close()
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('new2 complete source typography/footer/structure verified at five widths; ten secondary routes, mobile keyboard menu, real stored enquiries, failure recovery and authenticated admin inbox passed.')

if __name__=='__main__':main()
