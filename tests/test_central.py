"""Real PostgreSQL constraints/concurrency plus durable local crash injection.

Uses a uniquely named database on a disposable cluster, NEVER drops public or an
existing database. Set CENTRAL_TEST_CLUSTER_URL to enable database tests.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID,uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine,text

from central import service as s
from central.bootstrap import seed
from central.processes import deliver_one,recovery_pause
from central.simulator import Journal


@pytest.fixture
def pg():
    url=os.getenv('CENTRAL_TEST_CLUSTER_URL')
    if not url:
        pytest.skip('CENTRAL_TEST_CLUSTER_URL not configured')
    cluster=create_engine(url,isolation_level='AUTOCOMMIT')
    name='central_test_'+uuid4().hex
    with cluster.connect() as db:
        db.exec_driver_sql(f'CREATE DATABASE {name}')
    from sqlalchemy.engine import make_url
    engine=create_engine(make_url(url).set(database=name),pool_size=20,max_overflow=20)
    from alembic import command
    from alembic.config import Config
    config=Config(str(Path(__file__).parents[1]/'central/alembic.ini'))
    config.set_main_option('script_location',str(Path(__file__).parents[1]/'central/migrations'))
    config.set_main_option('sqlalchemy.url',engine.url.render_as_string(hide_password=False))
    command.upgrade(config,'head')
    command.upgrade(config,'head')  # Re-running migration is safe.
    yield engine
    engine.dispose()
    with cluster.connect() as db:
        db.exec_driver_sql(f'DROP DATABASE {name} WITH (FORCE)')
    cluster.dispose()


@pytest.fixture
def setup(pg,monkeypatch):
    monkeypatch.setenv('CENTRAL_SIMULATOR_ENABLED','true')
    monkeypatch.setenv('CENTRAL_SIMULATOR_SECRET','test-secret-only')
    with pg.begin() as db:
        data=seed(db,True)
    return data


def instructions(reference=None,amount=10000):
    return dict(external_reference=reference or str(uuid4()),amount_minor=amount,currency='USD',recipient='+252611234567',network='evc',corridor='EU-SO')


def admit(pg,data,payload=None,key=None):
    with pg.begin() as db:
        return s.admit(db,UUID(data['partner_id']),key or str(uuid4()),payload or instructions())


def claim(pg,data):
    with pg.begin() as db:
        return s.claim(db,UUID(data['worker_id']),UUID(data['device_id']))


def arm(pg,data,c):
    with pg.begin() as db:
        return s.arm(db,UUID(data['worker_id']),UUID(c['attempt_id']),c['lease_generation'],c['instruction_hash'])


def success(c):
    reference=str(uuid4())
    return dict(event_id=str(uuid4()),attempt_id=c['attempt_id'],lease_generation=c['lease_generation'],instruction_hash=c['instruction_hash'],
        outcome='SUCCESS',stage='AFTER_SEND',evidence_ref='simulator://verified',provider_reference=reference,
        proof=s.simulator_proof(c,reference,'test-secret-only'),occurred_at='2026-10-09T12:00:00Z')


def ingest(pg,data,r):
    with pg.begin() as db:
        return s.result(db,UUID(data['worker_id']),r)


def test_100_concurrent_duplicates(pg,setup):
    payload=instructions()
    with ThreadPoolExecutor(max_workers=20) as pool:
        results=list(pool.map(lambda _:admit(pg,setup,payload,'same-key'),range(100)))
    assert len({r['payout_id'] for r in results})==1
    with pg.begin() as db:
        pid=UUID(results[0]['payout_id'])
        assert s.row(db,'SELECT count(*) AS n FROM central.reservations WHERE payout_id=:id',id=pid)['n']==1
        assert s.row(db,'SELECT count(*) AS n FROM central.jobs WHERE payout_id=:id',id=pid)['n']==1
        assert s.row(db,'SELECT reserved_minor FROM central.accounts WHERE partner_id=:id',id=UUID(setup['partner_id']))['reserved_minor']==10060


def test_changed_key_reference_and_identical_payments(pg,setup):
    p=instructions()
    response=admit(pg,setup,p,'one')
    assert admit(pg,setup,p,'two')==response
    for key in ['one','new']:
        with pytest.raises(HTTPException) as error:
            admit(pg,setup,{**p,'amount_minor':20000},key)
        assert error.value.status_code==409
    assert admit(pg,setup,instructions())['payout_id']!=response['payout_id']
    with pg.begin() as db:
        other=seed(db,True)
    assert admit(pg,other,p,'one')['payout_id']!=response['payout_id']


def test_partner_cannot_overspend(pg,setup):
    with ThreadPoolExecutor(max_workers=10) as pool:
        def submit(_):
            try:
                return admit(pg,setup,instructions(amount=250000))
            except HTTPException as error:
                assert error.status_code==402
                return None
        results=list(pool.map(submit,range(10)))
    assert len([r for r in results if r])==3


def test_phone_claim_and_duplicate_success(pg,setup):
    admit(pg,setup)
    with ThreadPoolExecutor(max_workers=10) as pool:
        commands=list(pool.map(lambda _:claim(pg,setup),range(10)))
    commands=[c for c in commands if c]
    assert len(commands)==1
    c=commands[0]
    arm(pg,setup,c)
    r=success(c)
    with ThreadPoolExecutor(max_workers=10) as pool:
        results=list(pool.map(lambda _:ingest(pg,setup,r),range(10)))
    assert all(r['status']=='PAID' for r in results)
    with pg.begin() as db:
        assert s.row(db,'SELECT count(*) AS n FROM central.journals WHERE payout_id=:id',id=UUID(c['payout_id']))['n']==1
        assert s.row(db,"SELECT count(*) AS n FROM central.history WHERE payout_id=:id AND new_status='PAID'",id=UUID(c['payout_id']))['n']==1
    with pytest.raises(HTTPException):
        ingest(pg,setup,{**r,'outcome':'UNKNOWN'})
    assert ingest(pg,setup,{**r,'event_id':str(uuid4()),'outcome':'UNKNOWN'})['status']=='PAID'


@pytest.mark.parametrize('armed',[False,True])
def test_expiry_before_and_after_arm(pg,setup,armed):
    response=admit(pg,setup)
    c=claim(pg,setup)
    if armed:
        arm(pg,setup,c)
    with pg.begin() as db:
        s.run(db,"UPDATE central.jobs SET lease_until=now()-interval '1 second' WHERE payout_id=:id",id=UUID(response['payout_id']))
        s.reap(db)
        p=s.get_payout(db,UUID(response['payout_id']))
        assert p['status']==('UNKNOWN' if armed else 'QUEUED')
        assert s.row(db,"SELECT count(*) AS n FROM central.reservations WHERE payout_id=:id AND state='ACTIVE'",id=p['id'])['n']==(2 if armed else 1)
    with pytest.raises(HTTPException):
        arm(pg,setup,c)
    if armed:
        with pytest.raises(HTTPException):
            claim(pg,setup)
        assert ingest(pg,setup,success(c))['status']=='UNKNOWN'


def test_unknown_requires_independent_evidence_review(pg,setup):
    admit(pg,setup)
    c=claim(pg,setup)
    arm(pg,setup,c)
    report={**success(c),'outcome':'UNKNOWN','proof':None}
    assert ingest(pg,setup,report)['status']=='UNKNOWN'
    with pg.begin() as db:
        case=s.row(db,'SELECT * FROM central.cases WHERE payout_id=:id',id=UUID(c['payout_id']))
        s.propose(db,UUID(setup['reviewer_a_credential_id']),case['id'],'PAID','operator://verified/receipt','actual-receipt',True)
    with pytest.raises(HTTPException):
        with pg.begin() as db:
            s.approve(db,UUID(setup['reviewer_a_credential_id']),case['id'])
    for _ in range(2):
        with pg.begin() as db:
            assert s.approve(db,UUID(setup['reviewer_b_credential_id']),case['id'])['state']=='RESOLVED'
            assert s.get_payout(db,UUID(c['payout_id']))['status']=='PAID'


def test_cancel_revokes_arm_permission(pg,setup):
    response=admit(pg,setup)
    c=claim(pg,setup)
    with pg.begin() as db:
        assert s.cancel(db,UUID(setup['partner_id']),UUID(response['payout_id']))['status']=='CANCELLED'
    with pytest.raises(HTTPException):
        arm(pg,setup,c)


def test_posted_journal_balanced_immutable_and_restart(pg,setup):
    with pytest.raises(Exception,match='Unbalanced'):
        with pg.begin() as db:
            s.run(db,"INSERT INTO central.journals(id,business_event_key,event_type,evidence_ref) VALUES(:id,:key,'BAD','test')",id=uuid4(),key=str(uuid4()))
    with pg.begin() as db:
        entry=s.row(db,'SELECT * FROM central.entries LIMIT 1')
    with pytest.raises(Exception,match='append only'):
        with pg.begin() as db:
            s.run(db,'UPDATE central.entries SET amount_minor=1 WHERE id=:id',id=entry['id'])
    with pytest.raises(Exception,match='previously posted'):
        with pg.begin() as db:
            s.run(db,'INSERT INTO central.entries VALUES(:id,:journal,:account,:currency,1)',id=uuid4(),journal=entry['journal_id'],account=entry['account_id'],currency=entry['currency'])
    pg.dispose()  # Reconnect: all financial records must be durable.
    with pg.begin() as db:
        assert not s.run(db,'SELECT journal_id FROM central.entries GROUP BY journal_id,currency HAVING sum(amount_minor)<>0').all()
        assert not s.run(db,"""SELECT a.id FROM central.accounts a LEFT JOIN central.entries e ON e.account_id=a.id
            GROUP BY a.id HAVING a.balance_minor<>COALESCE(sum(CASE WHEN a.kind IN ('PARTNER_PAYABLE','FEES') THEN -e.amount_minor ELSE e.amount_minor END),0)""").all()


def test_webhook_failure_is_independent(pg,setup):
    with pg.begin() as db:
        s.run(db,"UPDATE central.partners SET webhook_url='https://example.invalid/events',webhook_secret='test' WHERE id=:id",id=UUID(setup['partner_id']))
    response=admit(pg,setup)
    assert deliver_one(pg,lambda *args:503)
    c=claim(pg,setup)
    arm(pg,setup,c)
    assert ingest(pg,setup,success(c))['status']=='PAID'
    with pg.begin() as db:
        assert s.get_payout(db,UUID(response['payout_id']))['status']=='PAID'


def test_restore_pause_is_conservative_even_before_arm(pg,setup):
    admit(pg,setup)
    c=claim(pg,setup)
    with pg.begin() as db:
        recovery_pause(db,'Test restore after potential external payment')
        assert s.get_payout(db,UUID(c['payout_id']))['status']=='UNKNOWN'
    with pytest.raises(HTTPException):
        arm(pg,setup,c)


@pytest.mark.parametrize('crash',['before_send','after_send'])
def test_worker_crash_does_not_repeat_payment(tmp_path,crash):
    path=str(tmp_path/'journal.sqlite3')
    command=dict(attempt_id=str(uuid4()),payout_id=str(uuid4()),lease_generation=1,instruction_hash='a'*64)
    sends=[]
    def send(c):
        sends.append(c['attempt_id'])
        return 'receipt'
    j=Journal(path)
    with pytest.raises(RuntimeError):
        j.execute(command,lambda _:None,send,'secret',crash)
    j.db.close()
    reboot=Journal(path)
    report=reboot.execute(command,lambda _:None,send,'secret')
    assert report['outcome']=='UNKNOWN'
    assert len(sends)==(1 if crash=='after_send' else 0)
    assert reboot.execute(command,lambda _:None,send,'secret')==report
    assert reboot.pending()[0][1]==report


def test_strict_api_validation():
    from central.app import Admission
    from pydantic import ValidationError
    assert Admission(**{**instructions(),'currency':' usd ','network':' EVC '}).currency=='USD'
    for extra in [{'amount_minor':100.1},{'amount_minor':True},{'partner_id':str(uuid4())},{'recipient':'0611234567'}]:
        with pytest.raises(ValidationError):
            Admission(**{**instructions(),**extra})


def test_http_commit_replay_auth_and_tenant_scope(pg,setup,monkeypatch):
    from fastapi.testclient import TestClient
    from central import app as api
    monkeypatch.setattr(api,'engine',lambda:pg)
    client=TestClient(api.app)
    headers={'Authorization':f"Bearer {setup['partner_token']}",'Idempotency-Key':'http-key'}
    payload=instructions()
    response=client.post('/v1/payouts',headers=headers,json=payload)
    assert response.status_code==202,response.text
    stored=response.json()
    assert client.get(stored['status_url'],headers=headers).json()['status']=='QUEUED'
    c=claim(pg,setup)
    arm(pg,setup,c)
    r=success(c)
    wh={'Authorization':f"Bearer {setup['worker_token']}"}
    assert client.post('/internal/v1/results',headers=wh,json=r).status_code==202
    assert client.get(stored['status_url'],headers=headers).json()['status']=='PAID'
    assert client.post('/v1/payouts',headers=headers,json=payload).json()==stored
    assert client.post('/v1/payouts',headers=headers,json={**payload,'amount_minor':200}).status_code==409
    with pg.begin() as db:
        other=seed(db,True)
    oh={'Authorization':f"Bearer {other['partner_token']}"}
    assert client.get(stored['status_url'],headers=oh).status_code==404
    assert client.post('/internal/v1/claim',headers=headers,json={'device_id':setup['device_id']}).status_code==403
    assert client.get(stored['status_url']).status_code==422


def test_cancel_arm_race(pg,setup):
    admit(pg,setup)
    c=claim(pg,setup)
    def cancel():
        try:
            with pg.begin() as db:
                return s.cancel(db,UUID(setup['partner_id']),UUID(c['payout_id']))
        except HTTPException as error:
            return error.status_code
    def arming():
        try:
            return arm(pg,setup,c)
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=[f.result() for f in [pool.submit(cancel),pool.submit(arming)]]
    assert sum(isinstance(r,dict) for r in results)==1
    with pg.begin() as db:
        p=s.get_payout(db,UUID(c['payout_id']))
        assert p['status'] in ('ARMED','CANCELLED')


def test_wallet_liquidity_guard(pg,setup):
    # Real statement loss can reduce float below reserved balances; record it,
    # then guarded assignment prevents further spending.
    with pg.begin() as db:
        wallet=s.row(db,'SELECT * FROM central.wallets WHERE id=:id',id=UUID(setup['wallet_id']))
        suspense=s.account(db,'suspense:USD','SUSPENSE','USD')
        s.post(db,'unexpected-loss','LOSS',[(wallet['account_id'],-999000),(suspense['id'],999000)],'operator://loss')
    response=admit(pg,setup)
    with pytest.raises(HTTPException) as error:
        claim(pg,setup)
    assert error.value.status_code==402
    with pg.begin() as db:
        assert s.row(db,"SELECT count(*) AS n FROM central.reservations WHERE payout_id=:id AND kind='WALLET'",id=UUID(response['payout_id']))['n']==0


def test_statement_debit_reclassified_without_double_accounting(pg,setup):
    admit(pg,setup)
    c=claim(pg,setup)
    arm(pg,setup,c)
    r={**success(c),'outcome':'UNKNOWN','provider_reference':None,'proof':None}
    ingest(pg,setup,r)
    items=[dict(operator_reference='real-debit',amount_minor=-10000,currency='USD',recipient='+252611234567',occurred_at='2026-10-09T12:00:00Z')]
    with pg.begin() as db:
        result=s.import_statement(db,UUID(setup['reviewer_a_credential_id']),UUID(setup['wallet_id']),'statement-1','operator://statement-1',items)
        assert s.import_statement(db,UUID(setup['reviewer_a_credential_id']),UUID(setup['wallet_id']),'statement-1','operator://statement-1',items)==result
        case=s.row(db,'SELECT * FROM central.cases WHERE payout_id=:id',id=UUID(c['payout_id']))
        s.propose(db,UUID(setup['reviewer_a_credential_id']),case['id'],'PAID','operator://statement-1','real-debit',True)
    with pg.begin() as db:
        s.approve(db,UUID(setup['reviewer_b_credential_id']),case['id'])
        wallet=s.row(db,'SELECT a.balance_minor FROM central.wallets w JOIN central.accounts a ON a.id=w.account_id WHERE w.id=:id',id=UUID(setup['wallet_id']))
        assert wallet['balance_minor']==990000
        assert s.row(db,"SELECT balance_minor FROM central.accounts WHERE business_key='suspense:USD'")['balance_minor']==0


def test_journal_business_key_conflict_and_funding_idempotency(pg,setup):
    with pg.begin() as db:
        first=s.funding(db,'admin','PARTNER',UUID(setup['partner_id']),'USD',50000,'deposit-123','bank://deposit-123')
    with pg.begin() as db:
        assert s.funding(db,'admin','PARTNER',UUID(setup['partner_id']),'USD',50000,'deposit-123','bank://deposit-123')==first
    with pytest.raises(HTTPException) as error:
        with pg.begin() as db:
            s.funding(db,'admin','PARTNER',UUID(setup['partner_id']),'USD',60000,'deposit-123','bank://deposit-123')
    assert error.value.status_code==409


def test_runtime_role_can_post_but_cannot_edit_financial_history(pg,setup):
    role='test_runtime_'+uuid4().hex
    sql=(Path(__file__).parents[1]/'central/roles.sql').read_text().replace('payout_runtime',role)
    with pg.begin() as db:
        db.exec_driver_sql(sql)
    try:
        with pg.begin() as db:
            db.exec_driver_sql(f'SET LOCAL ROLE {role}')
            r=s.admit(db,UUID(setup['partner_id']),'runtime-admit',instructions())
            c=s.claim(db,UUID(setup['worker_id']),UUID(setup['device_id']))
            s.arm(db,UUID(setup['worker_id']),UUID(c['attempt_id']),c['lease_generation'],c['instruction_hash'])
            assert s.result(db,UUID(setup['worker_id']),success(c))['status']=='PAID'
        for forbidden in ['UPDATE central.entries SET amount_minor=1', 'UPDATE central.accounts SET balance_minor=0', 'DELETE FROM central.journals']:
            with pytest.raises(Exception,match='permission denied'):
                with pg.begin() as db:
                    db.exec_driver_sql(f'SET LOCAL ROLE {role}')
                    db.exec_driver_sql(forbidden)
    finally:
        with pg.begin() as db:
            db.exec_driver_sql(f'DROP OWNED BY {role}')
            db.exec_driver_sql(f'DROP ROLE {role}')


def test_multiple_local_workers_cannot_repeat_command(tmp_path):
    from threading import Barrier
    command=dict(attempt_id=str(uuid4()),payout_id=str(uuid4()),lease_generation=1,instruction_hash='a'*64)
    path=str(tmp_path/'shared.sqlite3')
    initial=Journal(path)
    initial.record(command)
    initial.db.close()
    barrier=Barrier(2)
    sends=[]
    def execute():
        journal=Journal(path)
        barrier.wait()
        result=journal.execute(command,lambda _:None,lambda c:sends.append(c['attempt_id']) or 'receipt','secret')
        journal.db.close()
        return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(execute) for _ in range(2)]
        reports=[future.result() for future in futures]
    assert len(sends)<=1
    assert reports[0]['event_id']==reports[1]['event_id']


def test_complete_fake_worker_http_protocol(pg,setup,tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from central import app as api
    monkeypatch.setattr(api,'engine',lambda:pg)
    client=TestClient(api.app)
    ph={'Authorization':f"Bearer {setup['partner_token']}",'Idempotency-Key':'fake-http'}
    admitted=client.post('/v1/payouts',headers=ph,json=instructions())
    assert admitted.status_code==202
    wh={'Authorization':f"Bearer {setup['worker_token']}"}
    response=client.post('/internal/v1/claim',headers=wh,json={'device_id':setup['device_id']})
    assert response.status_code==200,response.text
    c=response.json()['command']
    def grant(command):
        response=client.post(f"/internal/v1/attempts/{command['attempt_id']}/arm",headers=wh,
                             json={k:command[k] for k in ('lease_generation','instruction_hash')})
        assert response.status_code==200,response.text
    journal=Journal(str(tmp_path/'http-worker.sqlite3'))
    r=journal.execute(c,grant,lambda _:'fake-operator-receipt','test-secret-only')
    for _ in range(2):
        accepted=client.post('/internal/v1/results',headers=wh,json=r)
        assert accepted.status_code==202,accepted.text
        assert accepted.json()['status']=='PAID'
    assert client.get(admitted.json()['status_url'],headers=ph).json()['status']=='PAID'
    ah={'Authorization':f"Bearer {setup['admin_token']}"}
    assert client.get('/internal/v1/metrics',headers=ah).status_code==200
    assert client.get('/v1/reports',headers=ph).status_code==200
    assert client.get('/health').status_code==200


def test_second_reported_debit_opens_incident_without_overwriting_paid(pg,setup):
    admit(pg,setup)
    c=claim(pg,setup)
    arm(pg,setup,c)
    assert ingest(pg,setup,success(c))['status']=='PAID'
    assert ingest(pg,setup,success(c))['status']=='PAID'  # another distinct provider receipt
    with pg.begin() as db:
        assert s.row(db,"SELECT reason FROM central.cases WHERE payout_id=:id",id=UUID(c['payout_id']))['reason']=='POSSIBLE_DEBIT_AFTER_FINALIZATION'
        assert s.row(db,'SELECT quarantined FROM central.devices WHERE id=:id',id=UUID(setup['device_id']))['quarantined']


@pytest.mark.parametrize('recorded_debit',[False,True])
def test_nonpayment_resolution_preserves_contradictory_operator_evidence(pg,setup,recorded_debit):
    admit(pg,setup)
    c=claim(pg,setup)
    arm(pg,setup,c)
    r={**success(c),'outcome':'UNKNOWN','proof':None,'provider_reference':'operator-ref'}
    ingest(pg,setup,r)
    with pg.begin() as db:
        if recorded_debit:
            s.import_statement(db,'operator-review',UUID(setup['wallet_id']),'sensitive-statement','operator://debit',[
                dict(operator_reference='operator-ref',amount_minor=-10000,currency='USD',recipient='+252611234567',occurred_at='2026-10-09T12:00:00Z')])
        case=s.row(db,'SELECT * FROM central.cases WHERE payout_id=:id',id=UUID(c['payout_id']))
        s.propose(db,UUID(setup['reviewer_a_credential_id']),case['id'],'FAILED','operator://nonpayment-proof',None,True)
    if recorded_debit:
        with pytest.raises(HTTPException,match='409'):
            with pg.begin() as db:
                s.approve(db,UUID(setup['reviewer_b_credential_id']),case['id'])
        with pg.begin() as db:
            assert s.get_payout(db,UUID(c['payout_id']))['status']=='UNKNOWN'
            assert s.row(db,"SELECT count(*) AS n FROM central.reservations WHERE payout_id=:id AND state='ACTIVE'",id=UUID(c['payout_id']))['n']==2
    else:
        with pg.begin() as db:
            s.approve(db,UUID(setup['reviewer_b_credential_id']),case['id'])
            assert s.get_payout(db,UUID(c['payout_id']))['status']=='FAILED'
            assert s.row(db,"SELECT count(*) AS n FROM central.reservations WHERE payout_id=:id AND state='ACTIVE'",id=UUID(c['payout_id']))['n']==0
