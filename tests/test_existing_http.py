"""Actual main:app HTTP boundary tests; no stubbed authentication middleware."""
import importlib
import sys
from uuid import UUID,uuid4
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
import pytest
import backend_core as c
from test_existing_backend import pg,setup,payload,report


@pytest.fixture
def client(pg,setup,monkeypatch):
    monkeypatch.setenv('DATABASE_URL',pg.url.render_as_string(hide_password=False))
    monkeypatch.setenv('SECRET_KEY','session-test-secret-'+'x'*32)
    monkeypatch.setenv('API_KEY_HASH_SECRET','legacy-setting')
    monkeypatch.setenv('EXECUTOR_TOKEN','legacy-token')
    monkeypatch.setenv('ENVIRONMENT','test')
    monkeypatch.setenv('SKIP_DB_BOOTSTRAP','true')
    monkeypatch.setenv('PARTNER_FEE','0.60')
    for name in ['main','database','config','auth_session','routes_ui_auth','middleware','schemas']:
        sys.modules.pop(name,None)
    main=importlib.import_module('main')
    yield TestClient(main.app),main
    main.engine.dispose()


def test_existing_routes_commit_replay_worker_contract_and_isolation(pg,setup,client):
    http,main=client
    headers={'X-API-Key':setup['key'],'Idempotency-Key':'http-submit'}
    p=payload().model_dump(mode='json')
    accepted=http.post('/payouts-create',headers=headers,json=p)
    assert accepted.status_code==201,accepted.text
    stored=accepted.json()
    assert http.post('/payouts-create',headers=headers,json=p).json()==stored
    assert http.post('/payouts-create',headers=headers,json={**p,'amount':'20.00'}).status_code==409
    assert http.get('/payouts/'+stored['id'],headers=headers).status_code==200
    wh={'Authorization':'Bearer '+setup['worker_token']}
    claimed=http.post('/internal/workers/v2/claim',headers=wh,json={'device_id':str(setup['device'])})
    assert claimed.status_code==200,claimed.text
    command=claimed.json()['command']
    armed=http.post('/internal/workers/v2/attempts/'+command['attempt_id']+'/arm',headers=wh,json={k:command[k] for k in ['lease_generation','instruction_hash']})
    assert armed.status_code==200,armed.text
    r=report(command)
    assert http.post('/internal/workers/v2/results',headers=wh,json=r).json()['status']=='SENT'
    assert http.post('/internal/workers/v2/results',headers=wh,json=r).json()['status']=='SENT'
    assert http.post('/payouts-create',headers=headers,json=p).json()==stored
    assert http.get('/payouts/'+stored['id'],headers=headers).json()['status']=='SENT'
    from security import generate_api_key
    key,prefix,verifier=generate_api_key()
    with pg.begin() as db:
        other=c.row(db,"INSERT INTO partners(name,api_key_prefix,api_key_hash) VALUES('Other',:prefix,:hash) RETURNING *",prefix=prefix,hash=verifier)
        first=c.opening_propose(db,other['id'],setup['admins'][0]['id'],0,0,'bank://zero-new-account')
        c.opening_approve(db,first['review_id'],setup['admins'][1]['id'])
    oh={'X-API-Key':key}
    assert http.get('/payouts/'+stored['id'],headers=oh).status_code==404
    assert http.post('/payouts/'+stored['id']+'/cancel',headers=oh).status_code==404
    assert http.get('/admin/api/partners',headers=oh).status_code==401
    assert http.get('/partner/webhook',headers=oh).json()=={'registered':False}


def test_browser_csrf_revocation_changed_roles_and_origin(pg,setup,client):
    http,main=client
    from browser_security import create
    with pg.begin() as db:
        token,csrf=create(db,setup['admins'][0]['id'],main.settings.secret_key)
    http.cookies.set('session',token)
    http.cookies.set('csrf_token',csrf)
    assert http.get('/admin/api/partners').status_code==200
    body=dict(scope='global',identity='all',paused=True,reason='Administrative pause')
    assert http.post('/admin/api/payment-controls',json=body).status_code==403
    assert http.post('/admin/api/payment-controls',headers={'X-CSRF-Token':csrf,'Origin':'https://evil.example'},json=body).status_code==403
    assert http.post('/admin/api/payment-controls',headers={'X-CSRF-Token':csrf},json=body).status_code==200
    with pg.begin() as db:
        c.run(db,"UPDATE users SET role='partner' WHERE id=:id",id=setup['admins'][0]['id'])
    assert http.get('/admin/api/partners').status_code==403
    with pg.begin() as db:
        c.run(db,"UPDATE users SET role='admin',is_active=false WHERE id=:id",id=setup['admins'][0]['id'])
    assert http.get('/admin/api/partners').status_code==401


def test_case_resolution_independent_current_proposal(pg,setup,client):
    http,main=client
    p=payload().model_dump(mode='json')
    assert http.post('/payouts-create',headers={'X-API-Key':setup['key']},json=p).status_code==201
    wh={'Authorization':'Bearer '+setup['worker_token']}
    command=http.post('/internal/workers/v2/claim',headers=wh,json={'device_id':str(setup['device'])}).json()['command']
    assert http.post('/internal/workers/v2/attempts/'+command['attempt_id']+'/arm',headers=wh,json={k:command[k] for k in ['lease_generation','instruction_hash']}).status_code==200
    assert http.post('/internal/workers/v2/results',headers=wh,json=report(command,'UNKNOWN')).json()['status']=='UNKNOWN'
    from browser_security import create
    tokens=[]
    with pg.begin() as db:
        case=c.row(db,'SELECT * FROM reconciliation_cases')
        for user in setup['admins']:
            tokens.append(create(db,user['id'],main.settings.secret_key))
    def login(index):
        http.cookies.set('session',tokens[index][0])
        return {'X-CSRF-Token':tokens[index][1]}
    path='/admin/api/reconciliation/'+str(case['id'])
    proposal=http.post(path+'/propose',headers=login(0),json=dict(decision='SENT',provider_reference='operator-record',evidence_ref='operator://verified/payment',stale_stopped=True))
    assert proposal.status_code==200,proposal.text
    assert http.post(path+'/approve',headers=login(0),json=proposal.json()).status_code==409
    wrong={'proposal_hash':'0'*64}
    assert http.post(path+'/approve',headers=login(1),json=wrong).status_code==409
    assert http.post(path+'/approve',headers=login(1),json=proposal.json()).status_code==200
    with pg.begin() as db:
        assert c.row(db,'SELECT status FROM payouts')['status']=='SENT'
        assert c.row(db,'SELECT count(*) AS n FROM ledger_journals WHERE payout_id IS NOT NULL')['n']==1


def test_containment_releases_physical_slot_but_not_financial_holds(pg,setup,client):
    http,main=client
    headers={'X-API-Key':setup['key']}
    for _ in range(2):
        assert http.post('/payouts-create',headers=headers,json=payload().model_dump(mode='json')).status_code==201
    wh={'Authorization':'Bearer '+setup['worker_token']}
    command=http.post('/internal/workers/v2/claim',headers=wh,json={'device_id':str(setup['device'])}).json()['command']
    http.post('/internal/workers/v2/attempts/'+command['attempt_id']+'/arm',headers=wh,json={k:command[k] for k in ['lease_generation','instruction_hash']})
    assert http.post('/internal/workers/v2/results',headers=wh,json=report(command,'UNKNOWN')).json()['status']=='UNKNOWN'
    assert http.post('/internal/workers/v2/claim',headers=wh,json={'device_id':str(setup['device'])}).json()['command'] is None
    from browser_security import create
    with pg.begin() as db:
        sessions=[create(db,u['id'],main.settings.secret_key) for u in setup['admins']]
    def login(i):
        http.cookies.set('session',sessions[i][0])
        return {'X-CSRF-Token':sessions[i][1]}
    proposal=http.post('/admin/api/attempts/'+command['attempt_id']+'/containment/propose',headers=login(0),json=dict(observed_minor=100000,evidence_ref='operator://verified-reset-float',physical_worker_neutralized=True))
    assert proposal.status_code==200,proposal.text
    path='/admin/api/containment/'+proposal.json()['review_id']+'/approve'
    assert http.post(path,headers=login(0)).status_code==409
    assert http.post(path,headers=login(1)).status_code==200
    http.cookies.clear()
    next_command=http.post('/internal/workers/v2/claim',headers=wh,json={'device_id':str(setup['device'])}).json()['command']
    assert next_command['payout_id']!=command['payout_id']
    with pg.begin() as db:
        assert c.row(db,'SELECT status FROM payouts WHERE id=:id',id=command['payout_id'])['status']=='UNKNOWN'
        assert c.row(db,'SELECT reserved_minor FROM ledger_accounts WHERE business_key=:key',key=f'wallet:{setup["wallet"]}')['reserved_minor']==2000
        assert c.row(db,"SELECT count(*) AS n FROM payout_reservations WHERE status='ACTIVE'")['n']==2


def test_later_financial_resolution_does_not_debit_observed_float_twice(pg,setup,client):
    http,main=client
    http.post('/payouts-create',headers={'X-API-Key':setup['key']},json=payload().model_dump(mode='json'))
    wh={'Authorization':'Bearer '+setup['worker_token']}
    cmd=http.post('/internal/workers/v2/claim',headers=wh,json={'device_id':str(setup['device'])}).json()['command']
    http.post('/internal/workers/v2/attempts/'+cmd['attempt_id']+'/arm',headers=wh,json={k:cmd[k] for k in ['lease_generation','instruction_hash']})
    http.post('/internal/workers/v2/results',headers=wh,json=report(cmd,'UNKNOWN'))
    from browser_security import create
    with pg.begin() as db:
        sessions=[create(db,u['id'],main.settings.secret_key) for u in setup['admins']]
        case=c.row(db,'SELECT id FROM reconciliation_cases')['id']
    def login(i):
        http.cookies.set('session',sessions[i][0])
        return {'X-CSRF-Token':sessions[i][1]}
    proposal=http.post('/admin/api/attempts/'+cmd['attempt_id']+'/containment/propose',headers=login(0),json=dict(observed_minor=99000,evidence_ref='operator://verified-reset-after-debit',physical_worker_neutralized=True))
    assert proposal.status_code==200
    assert http.post('/admin/api/containment/'+proposal.json()['review_id']+'/approve',headers=login(1)).status_code==200
    path='/admin/api/reconciliation/'+str(case)
    proposal=http.post(path+'/propose',headers=login(0),json=dict(decision='SENT',provider_reference='verified-later-receipt',evidence_ref='operator://verified/receipt',stale_stopped=True))
    assert proposal.status_code==200
    assert http.post(path+'/approve',headers=login(1),json=proposal.json()).status_code==200
    with pg.begin() as db:
        assert c.row(db,'SELECT observed_minor FROM payout_wallets')['observed_minor']==99000
        assert c.row(db,"SELECT balance_minor FROM ledger_accounts WHERE kind='WALLET'")['balance_minor']==99000
        assert c.row(db,'SELECT status FROM payouts')['status']=='SENT'
