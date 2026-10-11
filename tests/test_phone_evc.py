"""Real EVC bridge contract, using a disposable database and synthetic carrier text only."""
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from decimal import Decimal
import pytest
import backend_core as c
from test_existing_backend import pg, setup, payload, submit
from test_phone_worker import connection

@pytest.fixture
def real(pg, connection, monkeypatch):
    monkeypatch.setenv('PHONE_EVC_PAYMENTS_ENABLED','true')
    monkeypatch.setenv('SMS_PAYOUT_TEST_ENABLED','false')
    with pg.begin() as db:
        c.run(db,'UPDATE payment_workers SET simulator=false WHERE id=:id',id=connection['data']['worker']['id'])
    client=connection['client']
    response=client.post('/v1/evc/configure',json={'sim_subscription_id':2})
    assert response.status_code==200,response.text
    with pg.begin() as db:
        c.run(db,'UPDATE phone_evc_settings SET float_known=true')
    return connection

def job(pg, real):
    p=payload(provider='EVC',recipient='+252615738865',request_payload={'beneficiary':{'name':'SHUGRI AXAMAD CABDI','mobile':'+252615738865'}})
    result=submit(pg,real['data'],p)
    response=real['client'].post('/v1/claim',json={'wait_seconds':1})
    assert response.status_code==200,response.text
    j=response.json()['assignment']
    assert j and j['recipient_name']=='SHUGRI AXAMAD CABDI'
    assert real['client'].post('/v1/claim',json={'wait_seconds':1}).json()['assignment'] is None
    return j

def binding(j):
    return {k:j[k] for k in ('attempt_id','payload_hash','assignment_version')}

def event(j,sequence,phase,evidence=None):
    b=dict(binding(j),event_id=str(uuid4()),payout_id=j['payout_id'],sequence=sequence,phase=phase,at=int(datetime.now(timezone.utc).timestamp()*1000))
    if evidence is not None:b['evidence']=evidence
    return b

def prepare(real,j):
    client=real['client']
    assert client.post('/v1/assignment/ack',json=binding(j)).status_code==200
    for n,phase in enumerate(['RECEIVED','VALIDATED','READY','PREPARING'],1):
        r=client.post('/v1/events',json=event(j,n,phase));assert r.status_code==200,r.text
    r=client.post('/v1/authorize',json=binding(j));assert r.status_code==200,r.text
    assert client.post('/v1/authorize',json=binding(j)).status_code==409
    for n,phase in enumerate(['SUBMISSION_POSSIBLE','AWAITING_CONFIRMATION'],5):
        r=client.post('/v1/events',json=event(j,n,phase));assert r.status_code==200,r.text

def evidence(j,success=True):
    when=datetime.now(timezone(timedelta(hours=3))).strftime('%d/%m/%y %H:%M:%S')
    text=f'<-EVCPLUS- > $10 ayaad uwareejisay SHUGRI AXAMAD CABDI(615738865), Tar: {when}, Haraagaagu waa $990.' if success else 'Haraaga xisaabtaadu kuguma filna.'
    return dict(kind='SUCCESS_CONFIRMED' if success else 'NOT_PAID_CONFIRMED',code='EvcSuccess' if success else 'InsufficientBalance',payload_hash=j['payload_hash'],amount_minor=j['amount_minor'],currency='USD',carrier_response=text)

def test_real_success_capture_once_no_fabricated_receipt(pg,real):
    j=job(pg,real);prepare(real,j)
    body=event(j,7,'CONFIRMED_SUCCESS',evidence(j))
    for _ in range(2):
        r=real['client'].post('/v1/events',json=body);assert r.status_code==200,r.text
    with pg.begin() as db:
        assert c.row(db,'SELECT status FROM payouts WHERE id=:id',id=j['payout_id'])['status']=='SENT'
        assert c.row(db,'SELECT count(*) n FROM phone_evc_confirmations')['n']==1
        assert c.row(db,'SELECT count(*) n FROM provider_receipts')['n']==0
        assert c.row(db,"SELECT count(*) n FROM ledger_journals WHERE event_type='PAYOUT'")['n']==1
        assert c.row(db,'SELECT balance_available FROM partners')['balance_available']==Decimal('989.40')
        assert c.row(db,'SELECT observed_minor FROM payout_wallets')['observed_minor']==99000

@pytest.mark.parametrize('change',['name','amount','date'])
def test_mismatched_carrier_response_keeps_reservations(pg,real,change):
    j=job(pg,real);prepare(real,j);e=evidence(j)
    if change=='name':e['carrier_response']=e['carrier_response'].replace('SHUGRI','OTHER')
    if change=='amount':e['carrier_response']=e['carrier_response'].replace('$10 ','$11 ')
    if change=='date':
        current=datetime.now(timezone(timedelta(hours=3))).strftime('%d/%m/%y')
        e['carrier_response']=e['carrier_response'].replace(current,'01/01/20')
    assert real['client'].post('/v1/events',json=event(j,7,'CONFIRMED_SUCCESS',e)).status_code==409
    with pg.begin() as db:
        assert c.row(db,'SELECT status FROM payout_reservations')['status']=='ACTIVE'
        assert c.row(db,"SELECT count(*) n FROM ledger_journals WHERE event_type='PAYOUT'")['n']==0

def test_insufficient_balance_releases_without_fee(pg,real):
    j=job(pg,real);prepare(real,j)
    r=real['client'].post('/v1/events',json=event(j,7,'CONFIRMED_NOT_PAID',evidence(j,False)))
    assert r.status_code==200,r.text
    with pg.begin() as db:
        assert c.row(db,'SELECT status FROM payouts')['status']=='FAILED'
        assert c.row(db,'SELECT balance_available FROM partners')['balance_available']==1000

def test_unknown_never_reassigned(pg,real):
    j=job(pg,real);prepare(real,j)
    r=real['client'].post('/v1/events',json=event(j,7,'UNKNOWN',{'kind':'UNKNOWN','code':'Timeout'}))
    assert r.status_code==200,r.text
    r=real['client'].post('/v1/claim',json={'wait_seconds':1})
    assert r.status_code in (200,409)
    if r.status_code==200:assert r.json()['assignment'] is None
    with pg.begin() as db:
        assert c.row(db,'SELECT status FROM payouts')['status']=='UNKNOWN'
        assert c.row(db,'SELECT status FROM payout_reservations')['status']=='ACTIVE'

def test_unknown_initial_float_uses_only_carrier_observation(pg,real):
    with pg.begin() as db:
        wallet=c.row(db,'SELECT * FROM payout_wallets')
        opening=c.account(db,'test-opening-reversal','OPENING','USD')
        c.post(db,'test-reset-wallet','OPENING','USD',[(wallet['account_id'],-100000),(opening['id'],100000)],'test://disposable')
        c.run(db,'UPDATE payout_wallets SET observed_minor=0')
        c.run(db,'UPDATE phone_evc_settings SET float_known=false')
    j=job(pg,real);prepare(real,j)
    r=real['client'].post('/v1/events',json=event(j,7,'CONFIRMED_SUCCESS',evidence(j)))
    assert r.status_code==200,r.text
    with pg.begin() as db:
        assert c.row(db,'SELECT float_known FROM phone_evc_settings')['float_known'] is True
        assert c.row(db,"SELECT count(*) n FROM ledger_journals WHERE event_type='CARRIER_OBSERVED_OPENING'")['n']==1
        assert c.row(db,'SELECT observed_minor FROM payout_wallets')['observed_minor']==99000

def test_previous_sms_and_simulator_jobs_are_not_real_payments(pg,real,monkeypatch):
    monkeypatch.setenv('PHONE_EVC_PAYMENTS_ENABLED','false')
    submit(pg,real['data'])
    monkeypatch.setenv('PHONE_EVC_PAYMENTS_ENABLED','true')
    r=real['client'].post('/v1/claim',json={'wait_seconds':1})
    assert r.status_code==200,r.text
    assert r.json()['assignment'] is None
