"""Capture the actual localhost public pages with an isolated headless renderer."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-url',default='http://127.0.0.1:8000')
    parser.add_argument('--chromium',required=True)
    parser.add_argument('--widths',default='360,390,768,1280,1440')
    parser.add_argument('--pages',default='home,receive,partners,about,help,contact,track,privacy,terms,complaints')
    parser.add_argument('--output',default='.simulation-runs/hubaal-preview')
    parser.add_argument('--height',type=int,default=1100)
    parser.add_argument('--scale',type=float,default=1)
    args=parser.parse_args()
    if urlparse(args.base_url).hostname not in ('127.0.0.1','localhost'):
        raise SystemExit('Preview rendering is restricted to localhost')
    root=Path(__file__).resolve().parents[1];output=(root/args.output).resolve();output.mkdir(parents=True,exist_ok=True)
    report=[]
    with sync_playwright() as renderer:
        browser=renderer.chromium.launch(executable_path=args.chromium,headless=True)
        for page in args.pages.split(','):
            route='/'+page.removeprefix('home') if page=='home' or page.startswith(('home?','home#')) else '/'+page
            filename=page.replace('?lang=','-').replace('#','-').replace('/','-')
            for width in map(int,args.widths.split(',')):
                context=browser.new_context(viewport={'width':width,'height':args.height},device_scale_factor=args.scale)
                tab=context.new_page()
                errors=[];tab.on('pageerror',lambda error: errors.append(str(error)))
                response=tab.goto(args.base_url+route)
                assert response.status==200 and 'noindex' in response.headers.get('x-robots-tag','')
                if tab.locator('#hubaal-bootstrap').count():
                    tab.wait_for_selector('#root main h1')
                tab.evaluate('document.fonts.ready')
                tab.screenshot(path=str(output/(filename+'-'+str(width)+'.png')))
                assert not errors,errors
                assert tab.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
                html=tab.content();assert 'Hubaal Express' in html
                (output/(filename+'-'+str(width)+'.html')).write_text(html,encoding='utf-8')
                report.append({'route':route,'width':width,'device_scale':args.scale,'rendered':True,'page_errors':errors})
                context.close()
        browser.close()
    (output/'render-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(len(report),'actual localhost page renders captured:',output)


if __name__=='__main__':
    main()
