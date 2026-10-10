"""Render an offline preview of the real page with read-only localhost API snapshots.

No browser profile or interactive desktop is controlled. Chromium only renders
an isolated artifact; authentication is performed by the local HTTP test client.
"""
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse
import httpx


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-url',default='http://127.0.0.1:8000')
    parser.add_argument('--chromium',required=True)
    parser.add_argument('--output',default='.simulation-runs/earnings-preview')
    args=parser.parse_args()
    if urlparse(args.base_url).hostname not in ('127.0.0.1','localhost'):
        raise SystemExit('Preview is restricted to the owned localhost dashboard')
    root=Path(__file__).resolve().parents[1]
    output=(root/args.output).resolve();output.mkdir(parents=True,exist_ok=True)
    with httpx.Client(base_url=args.base_url,follow_redirects=True,timeout=60) as client:
        response=client.post('/login',data={'username':os.getenv('EARNINGS_PREVIEW_USER','demo-admin'),
          'password':os.environ['EARNINGS_PREVIEW_PASSWORD']})
        response.raise_for_status()
        data={}
        for path in ('/admin/api/funds/partners?limit=100','/admin/api/earnings?activity=simulation',
                     '/admin/api/earnings/details?activity=simulation&limit=50'):
            response=client.get(path);response.raise_for_status();data[path.split('?')[0]]=response.json()
        html=client.get('/admin/earnings').text
    for name in ('admin','earnings'):
        html=html.replace(f'<link rel="stylesheet" href="/static/{name}.css">',
           '<style>'+(root/f'static/{name}.css').read_text(encoding='utf-8')+'</style>')
    html=html.replace('<script src="/static/csrf.js" defer></script>','')
    html=html.replace('<script src="/static/earnings.js" defer></script>','')
    html=html.replace('<option value="simulation">','<option value="simulation" selected>')
    encoded=json.dumps(data).replace('<',chr(92)+'u003c')
    script='''window.addEventListener('error',e=>document.body.dataset.jsError=e.message);
    const snapshots=SNAPSHOTS;
    window.fetch=async url=>({ok:true,status:200,json:async()=>snapshots[String(url).split('?')[0]]});
    '''.replace('SNAPSHOTS',encoded)+(root/'static/earnings.js').read_text(encoding='utf-8')
    html=html.replace('</body>','<script>'+script+'</script></body>')
    artifact=output/'earnings-render.html';artifact.write_text(html,encoding='utf-8')
    for name,width,height in [('desktop',1440,2100),('mobile',390,1800)]:
        with tempfile.TemporaryDirectory(prefix='earnings-render-') as profile:
            result=subprocess.run([args.chromium,'--headless','--disable-gpu','--no-first-run',
              '--disable-background-networking',f'--user-data-dir={profile}',f'--window-size={width},{height}',
              '--virtual-time-budget=10000',f'--screenshot={output/name}.png','--dump-dom',artifact.as_uri()],
              capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60,
              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            dom=result.stdout
            if result.returncode or 'data-js-error=' in dom or 'Ledger report refreshed.' not in dom:
                raise RuntimeError('Offline page render failed; inspect isolated preview artifacts')
            assert '5520.00 USD' in dom and '180.00 USD' in dom
            (output/f'{name}-dom.html').write_text(dom,encoding='utf-8')
    print('Desktop and mobile earnings previews rendered successfully:',output)


if __name__=='__main__':
    main()
