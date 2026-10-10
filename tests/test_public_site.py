from html.parser import HTMLParser
from urllib.parse import urlsplit
import pytest
from pydantic import ValidationError
from test_existing_backend import pg,setup
from test_existing_http import client
from public_site.business import BUSINESS,BusinessConfig
from public_site.translations import TRANSLATIONS,available_languages


class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.ids=set()
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if a.get('id'):self.ids.add(a['id'])
        if tag=='a' and a.get('href'):self.links.append(a['href'])


def test_public_routes_brand_preview_policies_and_destinations(client):
    http,main=client
    routes=['/','/receive','/partners','/about','/help','/contact','/track','/privacy','/terms','/complaints','/partners/integration']
    cache={}
    for path in routes:
        r=http.get(path);assert r.status_code==200,r.text
        assert BUSINESS.brand in r.text and 'noindex' in r.headers['X-Robots-Tag']
        assert '<meta name="description"' in r.text
        assert 'Raspberry' not in r.text and 'USSD' not in r.text and 'HARDCODED_TOKEN' not in r.text
        assert 'application/ld+json' not in r.text
        parser=Links();parser.feed(r.text);cache[path]=parser
        if path in ('/privacy','/terms','/complaints'):assert 'Draft policy layout' not in r.text
    for path,parser in cache.items():
        for link in parser.links:
            parsed=urlsplit(link)
            if not parsed.scheme and not parsed.netloc:
                target=parsed.path or path
                response=http.get(target+('?' + parsed.query if parsed.query else ''))
                assert response.status_code in (200,303),link
                if parsed.fragment:
                    dest=Links();dest.feed(response.text);assert parsed.fragment in dest.ids,link
    assert http.get('/robots.txt').text=='User-agent: *\nDisallow: /\n'
    assert '<url>' not in http.get('/sitemap.xml').text


def test_complete_locales_and_live_readiness(client):
    http,_=client
    assert set(TRANSLATIONS['so'])==set(TRANSLATIONS['en'])
    assert all(TRANSLATIONS['so'].values())
    assert list(available_languages(False))==['en']
    r=http.get('/?lang=so');assert r.status_code==200
    assert '<html lang="so"' in r.text and 'Gaarsiinta lacagta gudaha' in r.text
    assert 'lang=so#enquiry' in r.text
    assert http.get('/?lang=ar').status_code==404
    with pytest.raises(ValidationError):BusinessConfig(launch_mode='live')
    with pytest.raises(ValidationError):BusinessConfig(service_mode='retail')
    with pytest.raises(ValidationError):BusinessConfig(portal_url='javascript:alert(1)')
    assert BUSINESS.quote_api is None and BUSINESS.sending_countries==()


def draft():
    return dict(company='Example Test Company',name='Example Contact',email='contact@example.test',
      website='https://example.test',countries='Somalia',volume='1000_10000',methods=['mobile_wallet'],
      message='Synthetic partnership enquiry for a local preview.')


def test_enquiry_validation_honest_preview_and_no_payment_writes(pg,client):
    from sqlalchemy import text
    http,_=client
    with pg.connect() as db:
        before={t:db.execute(text('SELECT count(*) FROM '+t)).scalar() for t in ('payouts','partners','ledger_journals')}
    good=http.post('/api/public/enquiries/preview',json=draft())
    assert good.status_code==200,good.text
    assert good.headers['Cache-Control']=='no-store'
    assert good.json()==dict(mode='preview',sent=False,stored=False,draft=draft())
    for changes in [dict(email='bad'),dict(website='javascript:alert(1)'),dict(methods=[]),dict(volume='anything'),dict(message='short'),dict(company=' '),dict(recipient='+252000000')]:
        assert http.post('/api/public/enquiries/preview',json={**draft(),**changes}).status_code==422
    assert http.post('/api/public/enquiries/preview',headers={'Origin':'https://unapproved.example'},json=draft()).status_code==403
    support=dict(name='Example Contact',email='help@example.test',topic='delivery',message='A synthetic request to explain a status.')
    assert http.post('/api/public/support/preview',json=support).json()['sent'] is False
    with pg.connect() as db:
        after={t:db.execute(text('SELECT count(*) FROM '+t)).scalar() for t in before}
    assert before==after


def test_public_tracking_is_synthetic_and_unknown_not_delivered(client):
    http,_=client
    unknown=http.get('/api/public/tracking/examples/action').json()
    assert unknown['mode']=='preview' and unknown['synthetic'] is True and unknown['status']=='UNKNOWN'
    assert all(s!='SENT' for s,_ in unknown['steps'])
    for scenario in ('processing','failed','delivered'):
        assert http.get('/api/public/tracking/examples/'+scenario).json()['reference'].startswith('HBX-DEMO-')
    assert http.get('/api/public/tracking/examples/real-reference').status_code==404
    assert http.get('/api/public/tracking/private-payout-id').status_code==404
    assert http.get('/track?reference=private-payout-id').status_code==200


def test_react_bootstrap_contains_only_public_configuration(client):
    http,_=client
    response=http.get('/api/public/site-bootstrap?lang=so')
    assert response.status_code==200
    assert response.headers['Cache-Control']=='no-store'
    data=response.json()
    assert data['lang']=='so' and data['preview'] is True
    assert data['brand']=='Hubaal' and data['portal_url']=='/login'
    assert data['licensing_disclosure']=='Hubaal is in the process of obtaining approval. Our payout service is not live yet.'
    assert data['copy']==TRANSLATIONS['so']
    assert {method.network for method in BUSINESS.payout_methods}=={'EVC Plus','ZAAD','eDahab','Salaam Bank','Premier Bank','Cash pickup'}
    assert 'SAHAL' not in response.text.upper()
    assert 'SAHAL' not in http.get('/api/public/site-bootstrap?lang=en').text.upper()
    assert set(data)=={'brand','legal_entity','contact','portal_url','licensing_disclosure',
        'preview','service_mode','lang','languages','copy','policies','api_docs','titles','descriptions'}
    assert 'SECRET_KEY' not in response.text and 'database_url' not in response.text
    assert http.get('/api/public/site-bootstrap?lang=ar').status_code==404
