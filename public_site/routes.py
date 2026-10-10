from datetime import datetime,timezone
import json
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import Response,JSONResponse
from fastapi.templating import Jinja2Templates
from .business import BUSINESS
from .translations import TRANSLATIONS,available_languages
from .fixtures import TRACKING_EXAMPLES
from .adapters import PartnerDraft,SupportDraft,local_preview

templates=Jinja2Templates(directory='templates')
PAGES={'/':'home','/receive':'receive','/partners':'partners','/about':'about','/help':'help',
       '/contact':'contact','/track':'track','/privacy':'privacy','/terms':'terms','/complaints':'complaints',
       '/partners/integration':'integration'}
TITLE_KEYS={'home':'hero_2','receive':'receive_title','partners':'partners_page_title','about':'about_title',
  'help':'help_page_title','contact':'contact_title','track':'track_title','privacy':'privacy',
  'terms':'terms','complaints':'complaints','integration':'integration_guide_title'}
DESCRIPTION_KEYS={'home':'hero_text','receive':'receive_intro','partners':'partners_page_intro','about':'about_intro',
 'help':'help_page_intro','contact':'contact_intro','track':'track_intro','privacy':'policy_intro',
 'terms':'policy_intro','complaints':'policy_intro','integration':'integration_security'}
CLIENT_KEYS=('required','validation_error','invalid_email','invalid_website','select_method','tracking_loading',
 'tracking_unavailable','checking','preview_ready','request_error','preview_unsent','search_results',
 'company','name','email','support_email','website','countries','volume','required_methods','message','support_topic',
 'mobile_wallet','other_method','volume_small','volume_medium','volume_large','volume_plus',
 'topic_delivery','topic_details','topic_other','status_received','status_processing','status_sent','status_failed',
 'status_unknown','status_unknown_note','status_processing_note','status_sent_note','status_failed_note')


def frontend_bootstrap(request, lang='en'):
    languages=available_languages(BUSINESS.launch_mode=='preview')
    if lang not in languages:
        raise HTTPException(404,'Language is not available')
    copy=TRANSLATIONS[lang]
    # Explicitly public configuration only. Never serialize application settings,
    # partner records, balances, authentication keys or callback signing secrets.
    return {
      'brand':BUSINESS.brand,'legal_entity':BUSINESS.legal_entity,'contact':BUSINESS.contact.model_dump(),
      'portal_url':BUSINESS.portal_url,'licensing_disclosure':BUSINESS.licensing_disclosure,
      'preview':BUSINESS.launch_mode=='preview','service_mode':BUSINESS.service_mode,
      'lang':lang,'languages':languages,'copy':copy,
      'policies':{p:getattr(BUSINESS,p+'_content') for p in ('privacy','terms','complaints')},
      'api_docs':BUSINESS.api_documentation_url or (request.app.docs_url if BUSINESS.launch_mode=='preview' else None),
      'titles':{path:copy[TITLE_KEYS[page]] for path,page in PAGES.items()},
      'descriptions':{path:copy[DESCRIPTION_KEYS[page]] for path,page in PAGES.items()},
    }


def frontend_assets():
    manifest=Path(__file__).resolve().parents[1]/'static/hubaal-react/.vite/manifest.json'
    if not manifest.is_file():
        return None
    entry=json.loads(manifest.read_text(encoding='utf-8'))['index.html']
    return {'js':'/static/hubaal-react/'+entry['file'],
            'css':['/static/hubaal-react/'+file for file in entry.get('css',[])]}


def render(request,path='/',lang='en'):
    languages=available_languages(BUSINESS.launch_mode=='preview')
    if lang not in languages:
        raise HTTPException(404,'Language is not available')
    page=PAGES[path];copy=TRANSLATIONS[lang]
    def link(destination):
        parsed=urlsplit(destination)
        if parsed.scheme or parsed.netloc or not destination.startswith('/'):
            return destination
        route,sep,anchor=destination.partition('#')
        result=route+('?' if '?' not in route else '&')+'lang='+lang
        return result+('#'+anchor if sep else '')
    assets=frontend_assets()
    response=templates.TemplateResponse(request=request,name='public/react.html' if assets else 'public/page.html',context={
      'request':request,'business':BUSINESS,'page':page,'copy':copy,'lang':lang,'languages':languages,
      'client_copy':{key:copy[key] for key in CLIENT_KEYS},
      'frontend_assets':assets,'bootstrap':frontend_bootstrap(request,lang),
      'link':link,'title':copy[TITLE_KEYS[page]],'description':copy[DESCRIPTION_KEYS[page]],
      'preview':BUSINESS.launch_mode=='preview','year':datetime.now(timezone.utc).year,
      'api_docs':BUSINESS.api_documentation_url or (request.app.docs_url if BUSINESS.launch_mode=='preview' else None),
      'structured_data':{'@context':'https://schema.org','@type':'Organization','name':BUSINESS.brand,
         'legalName':BUSINESS.legal_entity,'url':BUSINESS.website_url} if BUSINESS.legal_entity and BUSINESS.website_url else None,
      'policy_content':getattr(BUSINESS,page+'_content',()) if page in ('privacy','terms','complaints') else (),
    })
    if BUSINESS.launch_mode=='preview':
        response.headers['X-Robots-Tag']='noindex, nofollow, noarchive'
    return response


def make_router():
    router=APIRouter()
    @router.get('/api/public/site-bootstrap',include_in_schema=False)
    def site_bootstrap(request:Request,lang:str=Query('en',max_length=5)):
        return JSONResponse(frontend_bootstrap(request,lang),headers={'Cache-Control':'no-store',
          'X-Robots-Tag':'noindex, nofollow'})

    for path in PAGES:
        if path=='/':
            continue
        def endpoint_for(destination):
            def endpoint(request: Request,lang: str=Query('en',max_length=5)):
                return render(request,destination,lang)
            return endpoint
        router.add_api_route(path,endpoint_for(path),methods=['GET'],include_in_schema=False)

    @router.get('/robots.txt',include_in_schema=False)
    def robots():
        body='User-agent: *\nDisallow: /\n' if BUSINESS.launch_mode=='preview' else 'User-agent: *\nDisallow: /admin\nDisallow: /partner\nDisallow: /internal/\nDisallow: /api/\nDisallow: /login\nDisallow: /track\n'
        return Response(body,media_type='text/plain')

    @router.get('/sitemap.xml',include_in_schema=False)
    def sitemap():
        from xml.sax.saxutils import escape
        urls=[] if BUSINESS.launch_mode=='preview' else [BUSINESS.website_url.rstrip('/')+p for p in PAGES if p!='/track']
        return Response('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+
            ''.join('<url><loc>'+escape(url)+'</loc></url>' for url in urls)+'</urlset>',media_type='application/xml')

    def preview_only():
        if BUSINESS.launch_mode!='preview':
            raise HTTPException(404,'Preview examples are unavailable')

    @router.get('/api/public/tracking/examples/{scenario}',include_in_schema=False)
    def tracking_example(scenario: str):
        preview_only()
        if scenario not in TRACKING_EXAMPLES:
            raise HTTPException(404,'Example not found')
        return JSONResponse({'mode':'preview','synthetic':True,**TRACKING_EXAMPLES[scenario]},
          headers={'Cache-Control':'no-store','X-Robots-Tag':'noindex, nofollow'})

    @router.post('/api/public/enquiries/preview',include_in_schema=False)
    def enquiry(body: PartnerDraft):
        preview_only();return JSONResponse(local_preview(body),headers={'Cache-Control':'no-store','X-Robots-Tag':'noindex, nofollow'})

    @router.post('/api/public/support/preview',include_in_schema=False)
    def support(body: SupportDraft):
        preview_only();return JSONResponse(local_preview(body),headers={'Cache-Control':'no-store','X-Robots-Tag':'noindex, nofollow'})

    return router
