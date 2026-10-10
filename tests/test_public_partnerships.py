from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from sqlalchemy import text
from test_existing_backend import pg,setup
from test_existing_http import client

def enquiry(**changes):
    return dict(company_name='Synthetic website company',country='Somalia',contact_name='Test Contact',
        email='contact@example.test',monthly_volume='$10k – $100k / month',channels='All channels',**changes)

def test_committed_enquiry_replay_and_no_payment_writes(pg,client):
    http,_=client
    with pg.connect() as db:
        before={table:db.execute(text('SELECT count(*) FROM '+table)).scalar() for table in ('partners','payouts','ledger_journals')}
    headers={'Idempotency-Key':str(uuid4())}
    payload={**enquiry(),'channels':'Wallets + banks'}
    reply=http.post('/api/partnerships',json=payload,headers=headers)
    assert reply.status_code==201,reply.text
    assert reply.json()['received'] is True and reply.json()['reference'].startswith('HB-P-')
    assert reply.headers['Cache-Control']=='no-store'
    assert http.post('/api/partnerships',json=payload,headers=headers).json()==reply.json()
    assert http.post('/api/partnerships',json={**enquiry(),'country':'Kenya'},headers=headers).status_code==409
    with pg.connect() as db:
        stored=db.execute(text('SELECT * FROM public_partnership_enquiries')).mappings().one()
        assert stored['reference']==reply.json()['reference'] and stored['company_name']==enquiry()['company_name']
        assert all(db.execute(text('SELECT count(*) FROM '+table)).scalar()==count for table,count in before.items())


@pytest.mark.parametrize('channels', ['Cash pickup only', 'Wallets + banks + cash pickup'])
def test_cash_pickup_enquiries_are_stored_without_payment_writes(pg,client,channels):
    http,_=client
    with pg.connect() as db:
        before={table:db.execute(text('SELECT count(*) FROM '+table)).scalar() for table in ('partners','payouts','ledger_journals')}
    body={**enquiry(),'channels':channels}
    headers={'Idempotency-Key':str(uuid4())}
    received=http.post('/api/partnerships',json=body,headers=headers)
    assert received.status_code==201,received.text
    assert http.post('/api/partnerships',json=body,headers=headers).json()==received.json()
    with pg.connect() as db:
        assert db.execute(text('SELECT channels FROM public_partnership_enquiries')).scalar()==channels
        assert all(db.execute(text('SELECT count(*) FROM '+table)).scalar()==count for table,count in before.items())

@pytest.mark.parametrize('changes',[{'email':'bad'},{'company_name':' '},{'country':'x'},{'contact_name':'a'*101},
    {'monthly_volume':'unknown'},{'channels':'unknown'},{'channels':'Unsupported receiving channel'},
    {'email':'a\r\nb@example.test'},{'recipient':'private recipient'}])
def test_invalid_enquiries_do_not_store(pg,client,changes):
    http,_=client
    assert http.post('/api/partnerships',json={**enquiry(),**changes}).status_code==422
    with pg.connect() as db:
        assert db.execute(text('SELECT count(*) FROM public_partnership_enquiries')).scalar()==0

def test_admin_isolation_escaping_and_browser_csrf(pg,setup,client):
    http,main=client
    assert http.get('/admin/partnerships').status_code==401
    assert http.post('/api/partnerships',json=enquiry(),headers={'Origin':'https://unapproved.example'}).status_code==403
    from browser_security import create
    with pg.begin() as db:
        token,csrf=create(db,setup['admins'][0]['id'],main.settings.secret_key)
    http.cookies.set('session',token);http.cookies.set('csrf_token',csrf)
    malicious={**enquiry(),'company_name':'<script>alert(1)</script>'}
    assert http.post('/api/partnerships',json=malicious).status_code==403
    assert http.post('/api/partnerships',json=malicious,headers={'X-CSRF-Token':csrf}).status_code==201
    admin=http.get('/admin/partnerships')
    assert admin.status_code==200 and admin.headers['Cache-Control']=='no-store'
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in admin.text
    assert '<script>alert(1)</script>' not in admin.text
    with pg.begin() as db:
        db.execute(text("UPDATE users SET role='partner' WHERE id=:id"),{'id':setup['admins'][0]['id']})
    assert http.get('/admin/partnerships').status_code==403

def test_concurrent_retries_store_once(pg,client):
    http,_=client;headers={'Idempotency-Key':str(uuid4())}
    with ThreadPoolExecutor(max_workers=8) as workers:
        replies=list(workers.map(lambda _:http.post('/api/partnerships',json=enquiry(),headers=headers),range(8)))
    assert all(r.status_code==201 for r in replies),[r.text for r in replies]
    assert len({r.json()['reference'] for r in replies})==1
    with pg.connect() as db:
        assert db.execute(text('SELECT count(*) FROM public_partnership_enquiries')).scalar()==1

def test_shared_submission_quota(pg,client):
    http,_=client
    for _ in range(10):
        assert http.post('/api/partnerships',json=enquiry()).status_code==201
    limited=http.post('/api/partnerships',json=enquiry())
    assert limited.status_code==429 and limited.headers['Retry-After']=='60'
    with pg.connect() as db:
        assert db.execute(text('SELECT count(*) FROM public_partnership_enquiries')).scalar()==10
