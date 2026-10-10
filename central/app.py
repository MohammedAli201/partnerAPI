"""Run `uvicorn central.app:app`; migrations are explicit, never on startup."""
import hashlib
import os
import re
import time
import threading
from collections import Counter
from datetime import datetime
from functools import lru_cache
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import create_engine

from central import service as s


@lru_cache
def engine():
    url=os.environ['CENTRAL_DATABASE_URL']
    if url.startswith('postgresql://'):
        url=url.replace('postgresql://','postgresql+psycopg://',1)
    return create_engine(url,pool_pre_ping=True,pool_size=12,max_overflow=8,
        connect_args={'options':'-c statement_timeout=10000 -c lock_timeout=8000'})


def transaction():
    # Commit completes before the endpoint returns (not dependency teardown).
    return engine().begin()


def identity(authorization: str = Header(...)):
    if not authorization.startswith('Bearer ') or len(authorization)<39:
        s.fail(401,'Bearer credential required')
    hashed=hashlib.sha256(authorization[7:].encode()).hexdigest()
    with transaction() as db:
        who=s.row(db,'SELECT * FROM central.credentials WHERE token_hash=:hash AND revoked_at IS NULL',hash=hashed)
    if not who:
        s.fail(401,'Invalid credential')
    return dict(who)


def role(name):
    def dependency(who=Depends(identity)):
        if who['role']!=name:
            s.fail(403,'Credential scope denied')
        return who
    return dependency


partner=role('partner')
worker=role('worker')
reviewer=role('reviewer')
admin=role('admin')


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid')


class Admission(Strict):
    external_reference: str=Field(min_length=1,max_length=128)
    amount_minor: int=Field(strict=True,gt=0,le=1_000_000_000_000)
    currency: Literal['USD','EUR','GBP']
    recipient: str=Field(min_length=8,max_length=16)
    network: str=Field(min_length=1,max_length=64)
    corridor: str=Field(min_length=5,max_length=16)

    @field_validator('external_reference','recipient','network','corridor','currency',mode='before')
    @classmethod
    def normalize(cls,value,info):
        if not isinstance(value,str):
            raise ValueError('String required')
        value=value.strip()
        if info.field_name in ('corridor','currency'):
            value=value.upper()
        if info.field_name=='network':
            value=value.lower()
        if info.field_name=='recipient' and not re.fullmatch(r'\+[1-9][0-9]{7,14}',value):
            raise ValueError('Recipient must be E.164; no guessing of country prefixes')
        if info.field_name=='corridor' and not re.fullmatch(r'(EU|GB|US)-SO',value):
            raise ValueError('Supported corridors: EU-SO, GB-SO, US-SO')
        return value


class Claim(Strict):
    device_id: UUID


class Lease(Strict):
    lease_generation: int=Field(strict=True,gt=0)


class Arm(Lease):
    instruction_hash: str=Field(pattern=r'^[0-9a-f]{64}$')


class Result(Arm):
    event_id: UUID
    attempt_id: UUID
    outcome: Literal['SUCCESS','DEFINITE_FAILURE_BEFORE_SEND','UNKNOWN']
    stage: Literal['BEFORE_ARM','BEFORE_SEND','AFTER_SEND','UNKNOWN']
    evidence_ref: str=Field(min_length=1,max_length=512)
    provider_reference: str | None=Field(default=None,max_length=256)
    proof: str | None=Field(default=None,max_length=64)
    occurred_at: datetime

    @field_validator('occurred_at')
    @classmethod
    def timezone_required(cls,value):
        if value.tzinfo is None:
            raise ValueError('Timezone required')
        return value


class Proposal(Strict):
    decision: Literal['PAID','FAILED']
    evidence_ref: str=Field(min_length=1,max_length=512)
    provider_reference: str | None=None
    stale_execution_neutralized: bool


class Pause(Strict):
    scope: Literal['global','network','wallet','partner']
    identity: str=Field(min_length=1,max_length=64)
    paused: bool
    reason: str=Field(min_length=8,max_length=512)


class Funding(Strict):
    kind: Literal['PARTNER','WALLET']
    identity: UUID
    currency: Literal['USD','EUR','GBP']
    amount_minor: int=Field(strict=True,gt=0,le=1_000_000_000_000)
    reference: str=Field(min_length=1,max_length=256)
    evidence_ref: str=Field(min_length=1,max_length=512)


class StatementItem(Strict):
    operator_reference: str=Field(min_length=1,max_length=256)
    amount_minor: int=Field(strict=True,lt=0,ge=-1_000_000_000_000)
    currency: Literal['USD','EUR','GBP']
    recipient: str=Field(min_length=1,max_length=64)
    occurred_at: datetime

    @field_validator('occurred_at')
    @classmethod
    def timezone_required(cls,value):
        if value.tzinfo is None:
            raise ValueError('Timezone required')
        return value


class Statement(Strict):
    wallet_id: UUID
    source_reference: str=Field(min_length=1,max_length=256)
    evidence_ref: str=Field(min_length=1,max_length=512)
    items: list[StatementItem]=Field(min_length=1,max_length=1000)


class Observation(Strict):
    observed_minor: int=Field(strict=True,ge=0)
    evidence_ref: str=Field(min_length=1,max_length=512)


class IdleInspection(Strict):
    evidence_ref: str=Field(min_length=8,max_length=512)


app=FastAPI(title='Central payout backend',version='1.0.0')
_metric_lock=threading.Lock()
_admission_counts=Counter()
_latency_buckets=Counter()


@app.middleware('http')
async def admission_metrics(request,call_next):
    started=time.perf_counter()
    response=await call_next(request)
    if request.method=='POST' and request.url.path=='/v1/payouts':
        elapsed=time.perf_counter()-started
        with _metric_lock:
            _admission_counts[str(response.status_code)]+=1
            for boundary in (.01,.05,.1,.25,.5,1,2,5,float('inf')):
                if elapsed<=boundary:
                    _latency_buckets[str(boundary)]+=1
    return response


@app.get('/health')
def health():
    with transaction() as db:
        s.run(db,'SELECT 1')
    return dict(status='healthy')


@app.post('/v1/payouts',status_code=202)
def admit(payload: Admission,idempotency_key: str=Header(...,min_length=1,max_length=128),who=Depends(partner)):
    if idempotency_key!=idempotency_key.strip():
        s.fail(422,'Idempotency-Key must not have surrounding whitespace')
    with transaction() as db:
        response=s.admit(db,who['partner_id'],idempotency_key,payload.model_dump())
    return response


@app.get('/v1/payouts/{payout_id}')
def status(payout_id: UUID,who=Depends(partner)):
    with transaction() as db:
        p=s.get_payout(db,payout_id,who['partner_id'])
        response={k:p[k] for k in ('id','external_reference','status','status_version','amount_minor','fee_minor','currency','hold_reason','created_at','updated_at')}
    return response


@app.post('/v1/payouts/{payout_id}/cancel')
def cancel(payout_id: UUID,who=Depends(partner)):
    with transaction() as db:
        response=s.cancel(db,who['partner_id'],payout_id)
    return response


@app.get('/v1/reports')
def report(who=Depends(partner)):
    with transaction() as db:
        counts=s.run(db,'SELECT status,count(*) AS count,sum(amount_minor) AS amount_minor,sum(fee_minor) AS fees_minor,currency FROM central.payouts WHERE partner_id=:id GROUP BY status,currency',id=who['partner_id']).mappings().all()
        balances=s.run(db,'SELECT currency,balance_minor,reserved_minor,balance_minor-reserved_minor AS available_minor FROM central.accounts WHERE partner_id=:id',id=who['partner_id']).mappings().all()
    return dict(payouts=[dict(r) for r in counts],funding=[dict(r) for r in balances])


@app.post('/internal/v1/claim')
def claim(payload: Claim,who=Depends(worker)):
    with transaction() as db:
        response=s.claim(db,who['worker_id'],payload.device_id)
    return dict(command=response,poll_after_seconds=3)


@app.get('/internal/v1/attempts/{attempt_id}')
def attempt_status(attempt_id: UUID,who=Depends(worker)):
    with transaction() as db:
        a=s.row(db,'SELECT instructions,phase,generation FROM central.attempts WHERE id=:id AND worker_id=:worker',id=attempt_id,worker=who['worker_id'])
        if not a:
            s.fail(404,'Attempt not found')
        response=dict(a)
    return response


@app.post('/internal/v1/attempts/{attempt_id}/heartbeat')
def heartbeat(attempt_id: UUID,payload: Lease,who=Depends(worker)):
    with transaction() as db:
        response=s.heartbeat(db,who['worker_id'],attempt_id,payload.lease_generation)
    return response


@app.post('/internal/v1/attempts/{attempt_id}/arm')
def arm(attempt_id: UUID,payload: Arm,who=Depends(worker)):
    with transaction() as db:
        response=s.arm(db,who['worker_id'],attempt_id,payload.lease_generation,payload.instruction_hash)
    return response


@app.post('/internal/v1/results',status_code=202)
def result(payload: Result,who=Depends(worker)):
    with transaction() as db:
        response=s.result(db,who['worker_id'],payload.model_dump(mode='json'))
    return response


@app.get('/internal/v1/cases')
def cases(who=Depends(reviewer)):
    with transaction() as db:
        response=s.run(db,"SELECT * FROM central.cases WHERE state<>'RESOLVED' ORDER BY created_at LIMIT 100").mappings().all()
    return [dict(r) for r in response]


@app.post('/internal/v1/cases/{case_id}/propose')
def propose(case_id: UUID,payload: Proposal,who=Depends(reviewer)):
    with transaction() as db:
        response=s.propose(db,who['id'],case_id,payload.decision,payload.evidence_ref,payload.provider_reference,payload.stale_execution_neutralized)
    return response


@app.post('/internal/v1/cases/{case_id}/approve')
def approve(case_id: UUID,who=Depends(reviewer)):
    with transaction() as db:
        response=s.approve(db,who['id'],case_id)
    return response


@app.post('/internal/v1/controls')
def pause(payload: Pause,who=Depends(admin)):
    with transaction() as db:
        s.money_lock(db)
        if payload.scope=='global' and payload.identity!='all':
            s.fail(422,'Global identity must be all')
        if payload.scope=='partner':
            changed=s.row(db,'UPDATE central.partners SET paused=:paused WHERE id=CAST(:id AS uuid) RETURNING id',paused=payload.paused,id=payload.identity)
            if not changed:
                s.fail(404,'Partner not found')
        else:
            s.run(db,'''INSERT INTO central.controls VALUES(:scope,:identity,:paused,:reason)
                ON CONFLICT(scope,identity) DO UPDATE SET paused=EXCLUDED.paused,reason=EXCLUDED.reason''',**payload.model_dump())
        s.audit(db,who['id'],'PAUSE_CHANGE',f'{payload.scope}:{payload.identity}',payload.reason)
    return dict(paused=payload.paused)


@app.get('/internal/v1/metrics')
def metrics(who=Depends(admin)):
    with transaction() as db:
        states=s.run(db,"SELECT status,count(*) AS count,extract(epoch FROM now()-min(created_at)) AS oldest_age_seconds FROM central.payouts GROUP BY status").mappings().all()
        devices=s.run(db,'SELECT enabled,quarantined,count(*) AS count FROM central.devices GROUP BY enabled,quarantined').mappings().all()
        liquidity=s.run(db,"SELECT business_key,currency,balance_minor,reserved_minor FROM central.accounts WHERE spendable").mappings().all()
        callbacks=s.row(db,"SELECT count(*) AS pending,sum(attempts) AS attempts FROM central.deliveries WHERE state<>'DELIVERED'")
        queue=s.row(db,"SELECT count(*) AS depth,extract(epoch FROM now()-min(created_at)) AS oldest_age_seconds FROM central.jobs WHERE state='READY'")
        expired=s.row(db,"SELECT count(*) AS count FROM central.jobs WHERE state='LEASED' AND lease_until<now()")
        completion=s.row(db,"SELECT count(*) AS paid_last_hour FROM central.payouts WHERE status='PAID' AND updated_at>now()-interval '1 hour'")
        differences=s.run(db,'SELECT w.id,w.observed_minor,a.balance_minor,w.observed_minor-a.balance_minor AS difference_minor,w.observed_at FROM central.wallets w JOIN central.accounts a ON a.id=w.account_id').mappings().all()
    with _metric_lock:
        admission=dict(responses=dict(_admission_counts),cumulative_latency_seconds=dict(_latency_buckets))
    return dict(payouts=[dict(r) for r in states],devices=[dict(r) for r in devices],liquidity=[dict(r) for r in liquidity],
        webhooks=dict(callbacks),queue=dict(queue),lease_expiry=dict(expired),completion=dict(completion),
        reconciliation_differences=[dict(r) for r in differences],admission_process_metrics=admission)


@app.post('/internal/v1/funding')
def funding(payload: Funding,who=Depends(admin)):
    with transaction() as db:
        response=s.funding(db,who['id'],payload.kind,payload.identity,payload.currency,payload.amount_minor,payload.reference,payload.evidence_ref)
    return response


@app.post('/internal/v1/statements',status_code=202)
def statement(payload: Statement,who=Depends(reviewer)):
    with transaction() as db:
        response=s.import_statement(db,who['id'],payload.wallet_id,payload.source_reference,payload.evidence_ref,
                                    [item.model_dump(mode='json') for item in payload.items])
    return response


@app.post('/internal/v1/wallets/{wallet_id}/observe')
def observe(wallet_id: UUID,payload: Observation,who=Depends(reviewer)):
    with transaction() as db:
        s.money_lock(db)
        changed=s.row(db,'UPDATE central.wallets SET observed_minor=:amount,observed_at=now() WHERE id=:id RETURNING id',amount=payload.observed_minor,id=wallet_id)
        if not changed:
            s.fail(404,'Wallet not found')
        s.audit(db,who['id'],'OBSERVE_BALANCE',wallet_id,payload.evidence_ref)
    return dict(recorded=True)


@app.post('/internal/v1/devices/{device_id}/inspect-idle')
def inspect_idle(device_id: UUID,payload: IdleInspection,who=Depends(admin)):
    with transaction() as db:
        s.money_lock(db)
        if s.row(db,'SELECT 1 FROM central.attempts WHERE device_id=:id AND resolved_at IS NULL',id=device_id):
            s.fail(409,'Unresolved attempt prevents reuse')
        device=s.row(db,'UPDATE central.devices SET quarantined=false WHERE id=:id RETURNING *',id=device_id)
        if not device:
            s.fail(404,'Device not found')
        s.audit(db,who['id'],'INSPECT_IDLE',device_id,payload.evidence_ref)
    return dict(quarantined=False)


@app.post('/internal/v1/webhooks/{event_id}/replay')
def replay(event_id: UUID,who=Depends(admin)):
    with transaction() as db:
        changed=s.row(db,"UPDATE central.deliveries SET state='READY',next_attempt_at=now(),generation=generation+1,accepted_at=NULL WHERE event_id=:id RETURNING event_id",id=event_id)
        if not changed:
            s.fail(404,'Delivery not found')
        s.audit(db,who['id'],'REPLAY_WEBHOOK',event_id)
    return dict(queued=True)


@app.post('/internal/v1/wallets/{wallet_id}/resume')
def resume_wallet(wallet_id: UUID,payload: IdleInspection,who=Depends(admin)):
    with transaction() as db:
        s.money_lock(db)
        wallet=s.row(db,'SELECT w.*,a.balance_minor FROM central.wallets w JOIN central.accounts a ON a.id=w.account_id WHERE w.id=:id FOR UPDATE OF w,a',id=wallet_id)
        if not wallet:
            s.fail(404,'Wallet not found')
        if s.row(db,'SELECT 1 FROM central.attempts WHERE wallet_id=:id AND resolved_at IS NULL',id=wallet_id):
            s.fail(409,'Unresolved wallet attempt')
        if wallet['observed_minor']!=wallet['balance_minor'] or not wallet['observed_at'] or (datetime.now(wallet['observed_at'].tzinfo)-wallet['observed_at']).total_seconds()>3600:
            s.fail(409,'Fresh observed balance must match reconciled ledger')
        s.run(db,'UPDATE central.wallets SET enabled=true WHERE id=:id',id=wallet_id)
        s.audit(db,who['id'],'RESUME_RECONCILED_WALLET',wallet_id,payload.evidence_ref)
    return dict(enabled=True)
