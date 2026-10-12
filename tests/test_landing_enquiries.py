"""Supplied landing form: real storage, replay, validation and browser protection."""
from uuid import uuid4
import pytest
from sqlalchemy import text
from test_existing_backend import pg,setup
from test_existing_http import client

def payload(**changes):
    return dict(full_name='Test Partner',work_email='partner@example.test',company='Synthetic company',
        business_type='Fintech platform',country='Somalia',monthly_volume='Under $10k / month',
        channels=['EVC Plus','Bank transfer'],message='Synthetic integration enquiry',**changes)

def test_landing_enquiry_records_all_fields_once_and_keeps_payment_tables_untouched(pg,client):
    http,_=client
    with pg.connect() as db:
        counts={t:db.execute(text('SELECT count(*) FROM '+t)).scalar() for t in ('partners','payouts','ledger_journals')}
    headers={'Idempotency-Key':str(uuid4())};body=payload()
    r=http.post('/api/enquiries',json=body,headers=headers)
    assert r.status_code==201,r.text
    assert r.json()['received'] is True and r.json()['reference'].startswith('HB-P-')
    assert http.post('/api/enquiries',json=body,headers=headers).json()==r.json()
    assert http.post('/api/enquiries',json={**body,'channels':list(reversed(body['channels']))},headers=headers).json()==r.json()
    changed=dict(body,message='Different instructions')
    assert http.post('/api/enquiries',json=changed,headers=headers).status_code==409
    with pg.connect() as db:
        row=db.execute(text('SELECT * FROM public_partnership_enquiries')).mappings().one()
        assert row['contact_name']==body['full_name'] and row['email']==body['work_email']
        assert row['business_type']==body['business_type'] and row['message']==body['message']
        assert row['selected_channels']==sorted(body['channels'])
        assert row['channels']=='Wallets + banks'
        assert all(db.execute(text('SELECT count(*) FROM '+t)).scalar()==n for t,n in counts.items())

@pytest.mark.parametrize('change',[{'channels':[]},{'channels':['Unknown']},{'channels':['EVC Plus','EVC Plus']},
    {'work_email':'bad'},{'country':''},{'monthly_volume':''},{'business_type':'unknown'},{'message':'x'*4097},{'message':'bad\x00text'}])
def test_invalid_landing_submission_does_not_store(pg,client,change):
    http,_=client
    r=http.post('/api/enquiries',json={**payload(),**change})
    assert r.status_code==422,r.text
    with pg.connect() as db:assert db.execute(text('SELECT count(*) FROM public_partnership_enquiries')).scalar()==0

def test_landing_browser_csrf_admin_visibility_and_escaping(pg,setup,client):
    from browser_security import create
    http,main=client
    with pg.begin() as db:token,csrf=create(db,setup['admins'][0]['id'],main.settings.secret_key)
    http.cookies.set('session',token);http.cookies.set('csrf_token',csrf)
    body={**payload(), 'message':'<script>synthetic</script>'}
    assert http.post('/api/enquiries',json=body).status_code==403
    assert http.post('/api/enquiries',json=body,headers={'X-CSRF-Token':csrf}).status_code==201
    r=http.get('/admin/partnerships')
    assert r.status_code==200
    assert '&lt;script&gt;synthetic&lt;/script&gt;' in r.text and '<script>synthetic</script>' not in r.text
    assert body['business_type'] in r.text
