"""Security/financial tests on main:app and its existing public payout records."""
import hashlib
import importlib
import json
import os
import socket
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4,UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,text,inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config
import backend_core as c
import payment_worker as w
import webhook_transport as transport


@pytest.fixture(scope='session')
def pg():
    url=os.getenv('CENTRAL_TEST_CLUSTER_URL')
    if not url:
        pytest.skip('Explicit disposable PostgreSQL cluster required')
    cluster=create_engine(url,isolation_level='AUTOCOMMIT')
    name='existing_test_'+uuid4().hex
    with cluster.connect() as db:
        db.exec_driver_sql(f'CREATE DATABASE {name}')
    dburl=make_url(url).set(database=name)
    engine=create_engine(dburl,pool_size=24,max_overflow=20)
    root=Path(__file__).resolve().parents[1]
    config=Config(str(root/'alembic.ini'))
    config.set_main_option('script_location',str(root/'migrations'))
    config.set_main_option('sqlalchemy.url',dburl.render_as_string(hide_password=False))
    previous=os.environ.get('TEST_DATABASE_URL')
    os.environ['TEST_DATABASE_URL']=dburl.render_as_string(hide_password=False)
    try:
        command.upgrade(config,'head')
        command.upgrade(config,'head')
        yield engine
    finally:
        engine.dispose()
        if previous is None:
            os.environ.pop('TEST_DATABASE_URL',None)
        else:
            os.environ['TEST_DATABASE_URL']=previous
        with cluster.connect() as db:
            db.exec_driver_sql(f'DROP DATABASE {name} WITH (FORCE)')
        cluster.dispose()


@pytest.fixture
def setup(pg,monkeypatch):
    tables=[n for n in inspect(pg).get_table_names(schema='public') if n!='alembic_version']
    with pg.begin() as db:
        db.exec_driver_sql('TRUNCATE '+','.join('public."'+n+'"' for n in tables)+' RESTART IDENTITY CASCADE')
        c.run(db,"INSERT INTO payment_controls VALUES('global','all',false,'Disposable simulator test only')")
    monkeypatch.setenv('PAYOUT_SIMULATOR_ENABLED','true')
    monkeypatch.setenv('PAYOUT_SIMULATOR_SECRET','simulator-test-secret')
    monkeypatch.setenv('API_KEY_VERIFIER_SECRET','a'*48)
    from security import generate_api_key
    key,prefix,verifier=generate_api_key()
    worker_token='worker-secret-'+uuid4().hex
    with pg.begin() as db:
        partner=c.row(db,"INSERT INTO partners(name,api_key_prefix,api_key_hash,balance_available) VALUES('Partner',:prefix,:hash,1000) RETURNING *",prefix=prefix,hash=verifier)
        users=[c.row(db,"INSERT INTO users(username,password_hash,role,is_active,partner_id) VALUES(:name,'unused','admin',true,:partner) RETURNING *",name='admin'+str(i),partner=partner['id']) for i in range(2)]
        review=c.opening_propose(db,partner['id'],users[0]['id'],Decimal('1000'),Decimal('0'),'bank://reconciled-opening')
        c.opening_approve(db,review['review_id'],users[1]['id'])
        wid,wallet,did=[uuid4() for _ in range(3)]
        c.run(db,"INSERT INTO payment_workers(id,name,token_hash,simulator) VALUES(:id,'Fake Pi',:hash,true)",id=wid,hash=hashlib.sha256(worker_token.encode()).hexdigest())
        asset=c.account(db,f'wallet:{wallet}','WALLET','USD')
        opening=c.account(db,'wallet-opening:USD','OPENING','USD')
        c.post(db,f'wallet-opening:{wallet}','OPENING','USD',[(asset['id'],100000),(opening['id'],-100000)],'operator://opening')
        c.run(db,"INSERT INTO payout_wallets VALUES(:id,:reference,'USD',:account,true,100000,now())",id=wallet,reference=str(wallet),account=asset['id'])
        c.run(db,"INSERT INTO payout_devices VALUES(:id,:sim,:worker,:wallet,'Hormuud','evc',false,true)",id=did,sim=str(did),worker=wid,wallet=wallet)
    return dict(partner=partner['id'],key=key,admins=users,worker=dict(id=wid,simulator=True),worker_token=worker_token,wallet=wallet,device=did)


def payload(reference=None,amount='10.00',**overrides):
    from schemas import PayoutCreate
    values=dict(partner_tx_id=reference or str(uuid4()),amount=Decimal(amount),currency='USD',recipient='+252611234567',provider='Hormuud',payout_channel='evc',request_payload={})
    values.update(overrides)
    return PayoutCreate(**values)


def submit(pg,data,p=None,key=None):
    p=p or payload()
    with pg.begin() as db:
        return c.admission(db,data['partner'],p,p.partner_tx_id,key,Decimal('.60'))


def claim(pg,data):
    with pg.begin() as db:
        return w.claim(db,data['worker'],data['device'])


def arm(pg,data,command):
    with pg.begin() as db:
        return w.arm(db,data['worker'],UUID(command['attempt_id']),command['lease_generation'],command['instruction_hash'])


def report(command,outcome='SUCCESS'):
    reference=str(uuid4())
    return dict(attempt_id=command['attempt_id'],event_id=str(uuid4()),lease_generation=command['lease_generation'],instruction_hash=command['instruction_hash'],
        outcome=outcome,stage='AFTER_SEND',provider_reference=reference,evidence_ref='simulator://receipt',
        proof=w.proof(command,reference,'simulator-test-secret'),occurred_at='2026-10-09T12:00:00Z')


def test_concurrent_duplicates_changed_instructions_and_overspend(pg,setup):
    p=payload()
    with ThreadPoolExecutor(max_workers=20) as pool:
        replies=list(pool.map(lambda _:submit(pg,setup,p,'same'),range(100)))
    assert len({r['id'] for r in replies})==1
    with pg.begin() as db:
        for table in ['payouts','payout_queue','payout_reservations']:
            assert c.row(db,f'SELECT count(*) AS n FROM {table}')['n']==1
        assert c.row(db,'SELECT balance_reserved FROM partners WHERE id=:id',id=setup['partner'])['balance_reserved']==Decimal('10.60')
    for k in ['same','new-key',None]:
        with pytest.raises(HTTPException) as error:
            submit(pg,setup,payload(p.partner_tx_id,'20'),k)
        assert error.value.status_code==409
    with ThreadPoolExecutor(max_workers=10) as pool:
        def spend(_):
            try:
                return submit(pg,setup,payload(amount='400'))
            except HTTPException as error:
                assert error.status_code==402
                return None
        replies=list(pool.map(spend,range(10)))
    assert len([r for r in replies if r])==2


def test_legitimate_identical_transfers_new_reference(pg,setup):
    assert submit(pg,setup)['id']!=submit(pg,setup)['id']


def test_duplicate_receipt_accounting_and_unknown_hold(pg,setup):
    accepted=submit(pg,setup)
    with ThreadPoolExecutor(max_workers=10) as pool:
        commands=list(pool.map(lambda _:claim(pg,setup),range(10)))
    commands=[command for command in commands if command]
    assert len(commands)==1
    command=commands[0]
    arm(pg,setup,command)
    r=report(command)
    def ingest(_):
        with pg.begin() as db:
            return w.result(db,setup['worker'],r)
    with ThreadPoolExecutor(max_workers=10) as pool:
        assert all(reply['status']=='SENT' for reply in pool.map(ingest,range(10)))
    with pg.begin() as db:
        assert c.row(db,"SELECT count(*) AS n FROM ledger_journals WHERE event_type='PAYOUT'")['n']==1
        assert c.row(db,"SELECT count(*) AS n FROM payout_history WHERE new_status='SENT'")['n']==1
        assert c.row(db,'SELECT balance_available,balance_reserved FROM partners WHERE id=:id',id=setup['partner'])==dict(balance_available=Decimal('989.40'),balance_reserved=Decimal('0'))
    submit(pg,setup)
    command=claim(pg,setup)
    arm(pg,setup,command)
    with pg.begin() as db:
        assert w.result(db,setup['worker'],report(command,'UNKNOWN'))['status']=='UNKNOWN'
        assert c.row(db,'SELECT balance_reserved FROM partners WHERE id=:id',id=setup['partner'])['balance_reserved']==Decimal('10.60')
        assert c.row(db,'SELECT reserved_minor FROM ledger_accounts WHERE business_key=:key',key=f"wallet:{setup['wallet']}")['reserved_minor']==1000


@pytest.mark.parametrize('armed',[False,True])
def test_expiry_fencing_and_cancel(pg,setup,armed):
    accepted=submit(pg,setup)
    command=claim(pg,setup)
    if armed:
        arm(pg,setup,command)
    with pg.begin() as db:
        c.run(db,"UPDATE payout_queue SET lease_until=now()-interval '1 second'")
        w.reap(db)
        assert c.row(db,'SELECT status FROM payouts')['status']==('UNKNOWN' if armed else 'RECEIVED')
    with pytest.raises(HTTPException):
        arm(pg,setup,command)
    if armed:
        with pytest.raises(HTTPException):
            with pg.begin() as db:
                w.cancel(db,setup['partner'],UUID(accepted['id']))
    else:
        with pg.begin() as db:
            assert w.cancel(db,setup['partner'],UUID(accepted['id']))['status']=='CANCELLED'


@pytest.mark.parametrize('url',[
    'http://partner.example/hook','https://user:pass@partner.example/hook','https://partner.example:8443/hook',
    'https://127.0.0.1/hook','https://169.254.169.254/latest','https://10.0.0.1/hook','https://[::1]/hook',
    'https://[::ffff:127.0.0.1]/hook','https://[fe80::1]/hook','https://[64:ff9b::a00:1]/hook'])
def test_prohibited_registration(url):
    if url.startswith('https://') and '@' not in url and ':8443' not in url:
        with pytest.raises(ValueError):
            transport.resolve(url,resolver=lambda host,port,**kwargs:[(None,None,None,None,(host,443))])
    else:
        with pytest.raises(ValueError):
            transport.endpoint_url(url)


def test_dns_rebinding_and_redirect_do_not_connect_unapproved(monkeypatch):
    monkeypatch.setattr(transport,'resolve',lambda url:['1.1.1.1'])
    calls=[]
    class Connection:
        def __init__(self,host,address): calls.append((host,address))
        def request(self,*args,**kwargs): pass
        def getresponse(self): return type('Response',(),dict(status=302))()
        def close(self): pass
    monkeypatch.setattr(transport,'PinnedHTTPS',Connection)
    assert transport.send('https://partner.example/hook',['1.1.1.1'],b'{}',{})==302
    assert calls==[('partner.example','1.1.1.1')]
    monkeypatch.setattr(transport,'resolve',lambda url:['8.8.8.8'])
    with pytest.raises(ValueError,match='DNS changed'):
        transport.send('https://partner.example/hook',['1.1.1.1'],b'{}',{})
    assert len(calls)==1


def test_sessions_expiry_revocation_roles_and_disabled_users(pg,setup):
    from browser_security import create,verify,revoke
    secret='session-secret'
    with pg.begin() as db:
        token,csrf=create(db,setup['admins'][0]['id'],secret)
        assert verify(db,token,secret,csrf)['role']=='admin'
        c.run(db,"UPDATE users SET role='partner' WHERE id=:id",id=setup['admins'][0]['id'])
        assert verify(db,token,secret)['role']=='partner'
    with pytest.raises(HTTPException) as error:
        with pg.begin() as db:
            verify(db,token,secret,'bad-csrf')
    assert error.value.status_code==403
    with pg.begin() as db:
        revoke(db,token,secret)
    with pytest.raises(HTTPException):
        with pg.begin() as db:
            verify(db,token,secret)
    for field in ['expires_at','last_seen_at','disabled']:
        with pg.begin() as db:
            token,csrf=create(db,setup['admins'][1]['id'],secret)
            if field=='disabled':
                c.run(db,'UPDATE users SET is_active=false WHERE id=:id',id=setup['admins'][1]['id'])
            else:
                c.run(db,f"UPDATE browser_sessions SET {field}=now()-interval '13 hours'")
        with pytest.raises(HTTPException):
            with pg.begin() as db:
                verify(db,token,secret)


def test_callback_http_has_no_open_transaction_and_uses_partner_secret(pg,setup,monkeypatch):
    import registered_webhooks as callbacks
    from types import SimpleNamespace
    monkeypatch.setattr(callbacks,'resolve',lambda url:['1.1.1.1'])
    with pg.begin() as db:
        callbacks.register(db,setup['partner'],'https://partner.example/events','partner-secret-'+'x'*32,setup['admins'][0]['id'])
    submit(pg,setup)
    command=claim(pg,setup)
    session_factory=sessionmaker(bind=pg)
    active=[]
    def send(url,ips,raw,headers):
        with pg.begin() as db:
            # Delivery event row must be unlocked while HTTP is waiting.
            assert c.row(db,'SELECT * FROM payout_webhook_events FOR UPDATE NOWAIT')
        assert 'X-API-Key' not in headers
        assert ips==['1.1.1.1']
        active.append(raw)
        return 503
    monkeypatch.setattr(callbacks,'send',send)
    assert callbacks.deliver_next(session_factory,'internal-secret-must-not-be-used')
    assert len(active)==1
    arm(pg,setup,command)
    with pg.begin() as db:
        assert w.result(db,setup['worker'],report(command))['status']=='SENT'


def test_journal_balance_history_and_projection_guards(pg,setup):
    with pg.begin() as db:
        assert not c.run(db,'SELECT journal_id FROM ledger_entries GROUP BY journal_id HAVING sum(amount_minor)<>0').all()
    with pytest.raises(Exception,match='projections'):
        with pg.begin() as db:
            c.run(db,'UPDATE partners SET balance_available=1 WHERE id=:id',id=setup['partner'])
    with pytest.raises(Exception,match='append only'):
        with pg.begin() as db:
            c.run(db,'UPDATE ledger_entries SET amount_minor=1')
    with pytest.raises(Exception,match='Unbalanced'):
        with pg.begin() as db:
            c.run(db,"INSERT INTO ledger_journals(id,business_event_key,currency,event_type,evidence_ref) VALUES(:id,:key,'USD','BAD','test')",id=uuid4(),key=str(uuid4()))


def test_registered_retry_keeps_body_and_transaction_rollback(pg,setup,monkeypatch):
    import registered_webhooks as callbacks
    monkeypatch.setattr(callbacks,'resolve',lambda url:['1.1.1.1'])
    with pg.begin() as db:
        callbacks.register(db,setup['partner'],'https://partner.example/events','partner-secret-'+'x'*32,setup['admins'][0]['id'])
    submit(pg,setup)
    command=claim(pg,setup)
    bodies=[]
    def send(url,ips,raw,headers):
        bodies.append(raw)
        return 503 if len(bodies)==1 else 202
    monkeypatch.setattr(callbacks,'send',send)
    factory=sessionmaker(bind=pg)
    assert callbacks.deliver_next(factory)
    with pg.begin() as db:
        event=c.row(db,'SELECT * FROM payout_webhook_events')
        assert event['attempts']==1 and event['state']=='READY'
        c.run(db,'UPDATE payout_webhook_events SET next_attempt_at=now()')
    assert callbacks.deliver_next(factory)
    assert bodies[0]==bodies[1]
    with pg.begin() as db:
        assert c.row(db,'SELECT * FROM payout_webhook_events')['state']=='DELIVERED'
    with pytest.raises(RuntimeError):
        with pg.begin() as db:
            p=c.row(db,'SELECT * FROM payouts WHERE id=:id',id=command['payout_id'])
            c.change(db,p,'UNKNOWN','test','ROLLBACK')
            raise RuntimeError('abort')
    with pg.begin() as db:
        assert c.row(db,'SELECT count(*) AS n FROM payout_webhook_events')['n']==1
        assert c.row(db,'SELECT * FROM payouts')['status']=='PROCESSING'


def test_attempt_instructions_cannot_be_changed(pg,setup):
    submit(pg,setup)
    command=claim(pg,setup)
    with pytest.raises(Exception,match='immutable'):
        with pg.begin() as db:
            c.run(db,"UPDATE payout_attempts SET instruction_hash='changed' WHERE id=:id",id=command['attempt_id'])


def test_settlement_cannot_commit_without_financial_effect(pg,setup):
    accepted=submit(pg,setup)
    with pytest.raises(Exception,match='Settlement requires'):
        with pg.begin() as db:
            p=c.row(db,'SELECT * FROM payouts WHERE id=:id',id=accepted['id'])
            c.change(db,p,'SENT','bad-writer','MISSING_RECEIPT')
    with pg.begin() as db:
        assert c.row(db,'SELECT * FROM payouts')['status']=='RECEIVED'


def test_partner_quota_shared_across_connections_and_isolated(monkeypatch,pg,setup):
    import quotas
    monkeypatch.setattr(quotas.time,'time',lambda:1000000)
    def request(_):
        try:
            with pg.begin() as db:
                quotas.partner_quota(db,setup['partner'],'/payouts-create')
            return 200
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=30) as pool:
        responses=list(pool.map(request,range(60)))
    assert responses.count(200)==20 and responses.count(429)==40
    with pg.begin() as db:
        quotas.partner_quota(db,setup['partner']+100,'/payouts-create')


def test_late_old_attempt_evidence_freezes_current_ownership(pg,setup):
    submit(pg,setup)
    old=claim(pg,setup)
    with pg.begin() as db:
        c.run(db,"UPDATE payout_queue SET lease_until=now()-interval '1 second'")
        w.reap(db)
        c.run(db,'UPDATE payout_queue SET available_at=now()')
    current=claim(pg,setup)
    assert current['attempt_id']!=old['attempt_id']
    with pg.begin() as db:
        result=w.result(db,setup['worker'],report(old,'SUCCESS'))
        assert result['status']=='UNKNOWN'
        assert c.row(db,'SELECT * FROM payout_attempts WHERE id=:id',id=old['attempt_id'])['phase']=='NOT_SENT'
        assert c.row(db,'SELECT * FROM payout_attempts WHERE id=:id',id=current['attempt_id'])['phase']=='UNKNOWN'
        assert not c.row(db,'SELECT * FROM payout_wallets')['enabled']
    with pg.begin() as db:
        assert w.claim(db,setup['worker'],setup['device']) is None


def test_safe_prearm_retry_retains_partner_funding(pg,setup):
    submit(pg,setup)
    command=claim(pg,setup)
    event=report(command,'RETRYABLE_FAILURE_BEFORE_SEND')
    event['stage']='BEFORE_ARM'
    with pg.begin() as db:
        assert w.result(db,setup['worker'],event)['status']=='RECEIVED'
        assert c.row(db,'SELECT * FROM payout_reservations')['status']=='ACTIVE'
        assert c.row(db,'SELECT reserved_minor FROM ledger_accounts WHERE business_key=:key',key=f'wallet:{setup["wallet"]}')['reserved_minor']==0
        c.run(db,'UPDATE payout_queue SET available_at=now()')
    command2=claim(pg,setup)
    assert command2['attempt_id']!=command['attempt_id']
    arm(pg,setup,command2)
    with pg.begin() as db:
        assert w.result(db,setup['worker'],report(command2))['status']=='SENT'


def test_durable_fake_worker_crash(tmp_path):
    from worker_simulator import Journal
    journal=Journal(str(tmp_path/'worker.sqlite3'))
    command=dict(attempt_id=str(uuid4()),payout_id=str(uuid4()),lease_generation=1,instruction_hash='a'*64)
    sends=[]
    with pytest.raises(RuntimeError):
        journal.execute(command,lambda _:None,lambda _:sends.append(1) or 'receipt','secret',crash='after_send')
    journal.db.close()
    reboot=Journal(str(tmp_path/'worker.sqlite3'))
    assert reboot.execute(command,lambda _:None,lambda _:sends.append(1),'secret')['outcome']=='UNKNOWN'
    assert len(sends)==1
