"""Layout/focus/form checks in isolated artifacts using the actual frontend code."""
import argparse
import base64
import json
import re
import subprocess
import tempfile
from pathlib import Path
import httpx


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--chromium',required=True)
    parser.add_argument('--pages', default='/,/receive,/partners,/about,/help,/contact,/track,/privacy,/terms,/complaints,/partners/integration,/?lang=so,/partners?lang=so')
    parser.add_argument('--widths', default='360,390,768,1280,1440')
    parser.add_argument('--scale', type=float, default=1)
    parser.add_argument('--report', default='docs/hubaal-browser-validation.json')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    out=root/'.simulation-runs/hubaal-preview';out.mkdir(parents=True,exist_ok=True)
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=30) as client:
        pages={p:client.get(p).text for p in args.pages.split(',')}
        examples={n:client.get('/api/public/tracking/examples/'+n).json() for n in ['processing','action','delivered','failed']}
    css=(root/'static/hubaal/site.css').read_text(encoding='utf-8')
    for name in ['inter','manrope']:
        data=base64.b64encode((root/f'static/hubaal/fonts/{name}.woff2').read_bytes()).decode()
        css=css.replace(f'/static/hubaal/fonts/{name}.woff2','data:font/woff2;base64,'+data)
    code='\n'.join((root/p).read_text(encoding='utf-8') for p in ['static/hubaal/core.js','static/hubaal/site.js','tests/public_site_browser_checks.js'])
    shim='''window.fetch=async (url,options)=>{if(String(url).includes('/tracking/examples/'))return {ok:true,json:async()=>EXAMPLES[String(url).split('/').at(-1)]};
      if(window.__forceDraftFailure)return {ok:false,status:503,json:async()=>({detail:'Unavailable'})};
      return {ok:true,json:async()=>({mode:'preview',sent:false,stored:false,draft:JSON.parse(options.body)})}};
    '''.replace('EXAMPLES','('+json.dumps(examples)+')')
    report=[]
    for route,html in pages.items():
        html=html.replace('<link rel="stylesheet" href="/static/hubaal/site.css">','<style>'+css+'</style>')
        html=re.sub(r'<script src="/static/(?:csrf.js|hubaal/core.js|hubaal/site.js)" defer></script>','',html)
        for name in ['wordmark','courtyard','symbol']:
            html=html.replace('/static/hubaal/'+name+'.svg',(root/f'static/hubaal/{name}.svg').as_uri())
        html=html.replace('</body>','<script>'+shim+code+'</script></body>')
        name=route.strip('/').replace('/','-').replace('?lang=','-') or 'home'
        artifact=out/(name+'-checks.html');artifact.write_text(html,encoding='utf-8')
        for width in map(int,args.widths.split(',')):
            with tempfile.TemporaryDirectory(prefix='hubaal-check-',ignore_cleanup_errors=True) as profile:
                result=subprocess.run([args.chromium,'--headless','--disable-gpu','--no-first-run','--disable-background-networking',
                    f'--user-data-dir={profile}',f'--window-size={width},1000',f'--force-device-scale-factor={args.scale}','--virtual-time-budget=5000','--dump-dom',artifact.as_uri()],
                    capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                match=re.search(r'<script type="application/json" id="browser-check-results">(.*?)</script>',result.stdout,re.S)
                checks=json.loads(match.group(1)) if match else ['No check results']
                passed='data-checks="passed"' in result.stdout
                report.append({'route':route,'width':width,'device_scale':args.scale,'passed':passed,'checks':checks})
                if not passed:
                    (out/(name+'-'+str(width)+'-failure.html')).write_text(result.stdout,encoding='utf-8')
                    print('Failed',route,width,checks)
    (root/args.report).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(sum(r['passed'] for r in report),'/',len(report),'browser artifact checks passed')
    if not all(r['passed'] for r in report):raise SystemExit(1)


if __name__=='__main__':main()
