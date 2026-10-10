"""Compare integrated computed styles with the supplied production bundle."""
from pathlib import Path
import argparse, json
from playwright.sync_api import sync_playwright

PROPERTIES = [
    'fontFamily', 'fontSize', 'fontWeight', 'lineHeight', 'letterSpacing',
    'fontVariantNumeric', 'textTransform', 'color', 'backgroundColor',
    'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
    'marginTop', 'marginRight', 'marginBottom', 'marginLeft',
    'borderTopColor', 'borderTopWidth', 'borderRadius', 'columnGap', 'rowGap',
]
SECTIONS = ['top', 'channels', 'how-it-works', 'coverage', 'integration', 'about', 'partner-form']
COLLECT = """({properties, sections}) => {
 const result={};
 for(const name of [...sections,'footer','header']) {
  const root=name==='footer'||name==='header'?document.querySelector(name):document.getElementById(name);
  const values={};
  for(const element of [root,...root.querySelectorAll('[class]')]) {
   if(!element.className||typeof element.className!=='string')continue;
   const cls=element.className.trim().split(/\\s+/).sort().join(' ');
   if(values[cls])continue;
   const style=getComputedStyle(element);
   values[cls]=Object.fromEntries(properties.map(property=>[property,style[property]]));
  }
  result[name]=values;
 }
 return result;
}"""

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--chromium',required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    source=root/'.simulation-runs/hubaal-fron-source/frontend/build'
    out=root/'.simulation-runs/hubaal-fron-review';out.mkdir(exist_ok=True)
    html='''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/static/hubaal/fonts/hubaal-fonts.css">
<link rel="stylesheet" href="/__source/main.css"></head><body><div id="root"></div>
<script defer src="/__source/main.js"></script></body></html>'''
    results=[];differences=[];repairs=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=args.chromium,headless=True)
        for width in [360,390,768,1024,1440]:
            context=browser.new_context(viewport={'width':width,'height':1000},reduced_motion='reduce')
            reference=context.new_page()
            reference.route('http://127.0.0.1:8000/',lambda route:route.fulfill(body=html,content_type='text/html'))
            reference.route('**/__source/main.css',lambda route:route.fulfill(path=str(source/'static/css/main.0a471840.css'),content_type='text/css'))
            reference.route('**/__source/main.js',lambda route:route.fulfill(path=str(source/'static/js/main.30f26a32.js'),content_type='application/javascript'))
            reference.route('https://images.unsplash.com/**',lambda route:route.fulfill(path=str(root/'frontend/src/assets/new-photos/photo-1687422809654-579d81c29d32.jpg'),content_type='image/jpeg'))
            reference.goto('http://127.0.0.1:8000/');reference.wait_for_selector('h1');reference.evaluate('document.fonts.ready')
            integrated=context.new_page();integrated.goto('http://127.0.0.1:8000/');integrated.wait_for_selector('h1');integrated.evaluate('document.fonts.ready')
            expected=reference.evaluate(COLLECT,{'properties':PROPERTIES,'sections':SECTIONS})
            actual=integrated.evaluate(COLLECT,{'properties':PROPERTIES,'sections':SECTIONS})
            matches=0;omitted=[]
            for section,classes in expected.items():
                for cls,values in classes.items():
                    if cls not in actual[section]:
                        omitted.append({'section':section,'class':cls});continue
                    matches+=1
                    changes={property:{'reference':value,'integrated':actual[section][cls][property]} for property,value in values.items() if value!=actual[section][cls][property]}
                    if section=='coverage' and 'min-h-[420px]' in cls and changes=={'backgroundColor':{'reference':'rgba(0, 0, 0, 0)','integrated':'rgb(245, 246, 247)'}}:
                        repairs.append({'width':width,'reason':'Missing phone background utility repaired with the archived surface colour','changes':changes})
                        changes={}
                    if changes:differences.append({'width':width,'section':section,'class':cls,'changes':changes})
            results.append({'width':width,'compared_elements':matches,'intentional_class_adaptations':omitted,'reference':expected,'integrated':actual})
            if width in [390,1440]:reference.screenshot(path=str(out/f'original-home-{width}.png'))
            context.close()
        browser.close()
    (out/'source-style-comparison.json').write_text(json.dumps({'results':results,'differences':differences,'documented_rendering_repairs':repairs},indent=2),encoding='utf-8')
    print(json.dumps({'widths':len(results),'compared_elements':sum(result['compared_elements'] for result in results),'differences':differences,'documented_rendering_repairs':len(repairs)},indent=2))
    assert not differences, 'Integrated styles differ from the supplied production styles'

if __name__=='__main__':main()
