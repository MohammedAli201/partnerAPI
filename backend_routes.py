"""Additive routes attached to main:app; no second partner backend."""
import hashlib
from datetime import datetime,timezone
from typing import Literal
from uuid import UUID,uuid4
from decimal import Decimal
from fastapi import APIRouter,Depends,Header,HTTPException,Request
from pydantic import BaseModel,ConfigDict,Field,SecretStr,field_validator
import backend_core as c
import payment_worker as w


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid')

class Endpoint(Strict):
    partner_id: int
    url: str=Field(max_length=2048)
    signing_secret: SecretStr

class Opening(Strict):
    partner_id: int
    available: Decimal
    reserved: Decimal
    evidence_ref: str=Field(min_length=8,max_length=512)

class Correction(Strict):
    partner_id: int
    delta_minor: int=Field(strict=True,ge=-1000000000000,le=1000000000000)
    business_reference: str=Field(min_length=1,max_length=128)
    evidence_ref: str=Field(min_length=8,max_length=512)

class DeviceClaim(Strict):
    device_id: UUID

class Lease(Strict):
    lease_generation: int=Field(strict=True,gt=0)

class Arm(Lease):
    instruction_hash: str=Field(pattern='^[0-9a-f]{64}$')

class Result(Arm):
    event_id: UUID
    attempt_id: UUID
    outcome: Literal['SUCCESS','DEFINITE_FAILURE_BEFORE_SEND','RETRYABLE_FAILURE_BEFORE_SEND','UNKNOWN']
    stage: Literal['BEFORE_ARM','BEFORE_SEND','AFTER_SEND','UNKNOWN']
    provider_reference: str | None=Field(default=None,max_length=256)
    proof: str | None=Field(default=None,max_length=64)
    evidence_ref: str=Field(min_length=1,max_length=512)
    occurred_at: datetime
    @field_validator('occurred_at')
    @classmethod
    def aware(cls,value):
        if value.tzinfo is None:
            raise ValueError('Timezone required')
        return value

class CaseProposal(Strict):
    decision: Literal['SENT','FAILED']
    provider_reference: str | None=None
    evidence_ref: str=Field(min_length=8,max_length=512)
    stale_stopped: bool

class Approval(Strict):
    proposal_hash: str=Field(pattern='^[0-9a-f]{64}$')

class Containment(Strict):
    observed_minor: int=Field(strict=True,ge=0,le=1000000000000000)
    evidence_ref: str=Field(min_length=8,max_length=512)
    physical_worker_neutralized: Literal[True]

class Pause(Strict):
    scope: Literal['global','partner','network','wallet']
    identity: str
    paused: bool
    reason: str=Field(min_length=8,max_length=512)


def proposal_hash(case):
    return c.digest({key:str(case[key]) for key in ('decision','provider_reference','evidence_ref','proposer','stale_stopped')})


def make_router(partner_auth,require_role,get_db):
    router=APIRouter()
    admin=require_role('admin')
    def worker(authorization: str=Header(...),db=Depends(get_db)):
        if not authorization.startswith('Bearer '):
            c.fail(401,'Worker Bearer credential required')
        return w.authenticate(db,authorization[7:])

    def finish(db,function,*args):
        try:
            result=function(db,*args)
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise

    @router.post('/payouts/{payout_id}/cancel')
    def cancel(payout_id: UUID,partner=Depends(partner_auth),db=Depends(get_db)):
        return finish(db,w.cancel,partner.id,payout_id)

    @router.get('/partner/webhook')
    def endpoint(partner=Depends(partner_auth),db=Depends(get_db)):
        e=c.row(db,'SELECT id,url,version,enabled FROM webhook_endpoints WHERE partner_id=:id AND enabled',id=partner.id)
        return dict(e) if e else dict(registered=False)

    @router.post('/admin/api/webhooks/register')
    def register(payload: Endpoint,user=Depends(admin),db=Depends(get_db)):
        from registered_webhooks import register
        try:
            return finish(db,register,payload.partner_id,payload.url,payload.signing_secret.get_secret_value(),user['uid'])
        except ValueError:
            c.fail(422,'Webhook destination is prohibited or unresolved')

    @router.post('/admin/api/webhooks/{event_id}/replay')
    def replay(event_id: UUID,user=Depends(admin),db=Depends(get_db)):
        c.lock(db)
        e=c.row(db,'SELECT * FROM payout_webhook_events WHERE event_id=:id FOR UPDATE',id=event_id)
        if not e:
            c.fail(404,'Event not found')
        endpoint=c.row(db,'SELECT * FROM webhook_endpoints WHERE partner_id=:id AND enabled',id=e['partner_id'])
        if not endpoint:
            c.fail(409,'Approved partner endpoint required')
        c.run(db,"UPDATE payout_webhook_events SET endpoint_id=:endpoint,callback_url=:url,state='READY',accepted_at=NULL,next_attempt_at=now(),generation=generation+1 WHERE event_id=:id",id=event_id,endpoint=endpoint['id'],url=endpoint['url'])
        c.audit(db,user['uid'],'REPLAY_EVENT',event_id)
        db.commit()
        return dict(queued=True)

    @router.post('/admin/api/funds/opening/propose')
    def propose_opening(payload: Opening,user=Depends(admin),db=Depends(get_db)):
        return finish(db,c.opening_propose,payload.partner_id,user['uid'],payload.available,payload.reserved,payload.evidence_ref)

    @router.post('/admin/api/funds/opening/{review_id}/approve')
    def approve_opening(review_id: UUID,user=Depends(admin),db=Depends(get_db)):
        return finish(db,c.opening_approve,review_id,user['uid'])

    @router.post('/internal/workers/v2/claim')
    def claim(payload: DeviceClaim,worker=Depends(worker),db=Depends(get_db)):
        return dict(command=finish(db,w.claim,worker,payload.device_id),poll_after_seconds=3)

    @router.post('/admin/api/funds/corrections/propose')
    def propose_correction(payload: Correction,user=Depends(admin),db=Depends(get_db)):
        c.lock(db)
        p=c.row(db,'SELECT * FROM partners WHERE id=:id AND ledger_enabled',id=payload.partner_id)
        if not p or payload.delta_minor==0:
            c.fail(409,'Enabled account and nonzero correction required')
        prior=c.row(db,'SELECT * FROM correction_reviews WHERE partner_id=:partner AND business_reference=:reference',partner=p['id'],reference=payload.business_reference)
        if prior:
            if prior['delta_minor']!=payload.delta_minor or prior['evidence_ref']!=payload.evidence_ref:
                c.fail(409,'Correction reference changed')
            return dict(review_id=str(prior['id']))
        rid=uuid4()
        c.run(db,'INSERT INTO correction_reviews(id,partner_id,currency,delta_minor,business_reference,evidence_ref,proposer) VALUES(:id,:partner,:currency,:delta,:reference,:evidence,:user)',id=rid,partner=p['id'],currency=p['funding_currency'],delta=payload.delta_minor,reference=payload.business_reference,evidence=payload.evidence_ref,user=user['uid'])
        c.audit(db,user['uid'],'PROPOSE_CORRECTION',rid,payload.evidence_ref)
        db.commit()
        return dict(review_id=str(rid))

    @router.post('/admin/api/funds/corrections/{review_id}/approve')
    def approve_correction(review_id: UUID,user=Depends(admin),db=Depends(get_db)):
        c.lock(db)
        r=c.row(db,'SELECT * FROM correction_reviews WHERE id=:id FOR UPDATE',id=review_id)
        if not r or r['proposer']==user['uid']:
            c.fail(409,'Independent correction approval required')
        if r['approved_at']:
            return dict(approved=True)
        a=c.funding_account(db,r['partner_id'],r['currency'])
        if a['balance_minor']+r['delta_minor']<a['reserved_minor']:
            c.fail(409,'Correction would consume held funds; investigate separately')
        suspense=c.account(db,f"correction-suspense:{r['currency']}",'SUSPENSE',r['currency'])
        c.post(db,f"correction:{r['partner_id']}:{r['business_reference']}",'CORRECTION',r['currency'],[(a['id'],-r['delta_minor']),(suspense['id'],r['delta_minor'])],r['evidence_ref'])
        c.run(db,'UPDATE correction_reviews SET approver=:user,approved_at=now() WHERE id=:id',id=review_id,user=user['uid'])
        c.audit(db,user['uid'],'APPROVE_CORRECTION',review_id,r['evidence_ref'])
        db.commit()
        return dict(approved=True)

    @router.post('/internal/workers/v2/attempts/{attempt_id}/heartbeat')
    def heartbeat(attempt_id: UUID,payload: Lease,worker=Depends(worker),db=Depends(get_db)):
        return finish(db,w.heartbeat,worker,attempt_id,payload.lease_generation)

    @router.post('/internal/workers/v2/attempts/{attempt_id}/arm')
    def arm(attempt_id: UUID,payload: Arm,worker=Depends(worker),db=Depends(get_db)):
        return finish(db,w.arm,worker,attempt_id,payload.lease_generation,payload.instruction_hash)

    @router.get('/internal/workers/v2/attempts/{attempt_id}')
    def status(attempt_id: UUID,worker=Depends(worker),db=Depends(get_db)):
        a=c.row(db,'SELECT instructions,phase,generation FROM payout_attempts WHERE id=:id AND worker_id=:worker',id=attempt_id,worker=worker['id'])
        if not a:
            c.fail(404,'Attempt not found')
        return dict(a)

    @router.post('/internal/workers/v2/results',status_code=202)
    def result(payload: Result,worker=Depends(worker),db=Depends(get_db)):
        return finish(db,w.result,worker,payload.model_dump(mode='json'))

    @router.get('/admin/api/reconciliation')
    def cases(user=Depends(admin),db=Depends(get_db)):
        return [dict(r) for r in c.run(db,'SELECT * FROM reconciliation_cases WHERE resolved_at IS NULL ORDER BY created_at LIMIT 100').mappings().all()]

    @router.post('/admin/api/reconciliation/{case_id}/propose')
    def propose(case_id: UUID,payload: CaseProposal,user=Depends(admin),db=Depends(get_db)):
        c.lock(db)
        case=c.row(db,'SELECT * FROM reconciliation_cases WHERE id=:id FOR UPDATE',id=case_id)
        if not case or case['resolved_at']:
            c.fail(409,'Case unavailable')
        if not payload.stale_stopped or (payload.decision=='SENT' and not payload.provider_reference):
            c.fail(422,'Neutralize stale execution and provide verified payment evidence')
        case=c.row(db,'UPDATE reconciliation_cases SET decision=:decision,provider_reference=:provider_reference,evidence_ref=:evidence_ref,stale_stopped=:stale_stopped,proposer=:user WHERE id=:id RETURNING *',id=case_id,user=user['uid'],**payload.model_dump())
        c.audit(db,user['uid'],'PROPOSE_'+payload.decision,case_id,payload.evidence_ref)
        db.commit()
        return dict(proposal_hash=proposal_hash(case))

    @router.post('/admin/api/reconciliation/{case_id}/approve')
    def approve(case_id: UUID,payload: Approval,user=Depends(admin),db=Depends(get_db)):
        c.lock(db)
        case=c.row(db,'SELECT * FROM reconciliation_cases WHERE id=:id FOR UPDATE',id=case_id)
        if not case:
            c.fail(404,'Case unavailable')
        if case['resolved_at']:
            return dict(resolved=True)
        if not case['proposer'] or case['proposer']==user['uid'] or proposal_hash(case)!=payload.proposal_hash or not case['stale_stopped']:
            c.fail(409,'Independent approval of the current evidence is required')
        p=c.row(db,'SELECT * FROM payouts WHERE id=:id FOR UPDATE',id=case['payout_id'])
        a=c.row(db,'SELECT * FROM payout_attempts WHERE payout_id=:id AND resolved_at IS NULL FOR UPDATE',id=p['id'])
        if p['status']!='UNKNOWN' or not a:
            c.fail(409,'Legacy or extra-debit incident requires an operator-specific recovery adapter')
        if case['decision']=='SENT':
            w.paid(db,a,p,case['provider_reference'],case['evidence_ref'],user['uid'])
        else:
            c.release_partner(db,p)
            w.wallet_release(db,a,'RELEASED')
            c.run(db,"UPDATE payout_attempts SET phase='NOT_SENT',resolved_at=now() WHERE id=:id",id=a['id'])
            c.run(db,"UPDATE payout_queue SET status='DONE' WHERE payout_id=:id",id=p['id'])
            c.change(db,p,'FAILED',user['uid'],'INDEPENDENT_NONPAYMENT_EVIDENCE')
        c.run(db,'UPDATE reconciliation_cases SET approver=:user,resolved_at=now() WHERE id=:id',id=case_id,user=user['uid'])
        c.audit(db,user['uid'],'APPROVE_RESOLUTION',case_id,case['evidence_ref'])
        db.commit()
        return dict(resolved=True)

    @router.post('/admin/api/payment-controls')
    def pause(payload: Pause,user=Depends(admin),db=Depends(get_db)):
        c.lock(db)
        if payload.scope=='global' and payload.identity!='all':
            c.fail(422,'Global identity must be all')
        if payload.scope=='partner':
            changed=c.row(db,'UPDATE partners SET paused=:paused WHERE id=:id RETURNING id',id=int(payload.identity),paused=payload.paused)
            if not changed:
                c.fail(404,'Partner not found')
        else:
            c.run(db,'INSERT INTO payment_controls VALUES(:scope,:identity,:paused,:reason) ON CONFLICT(scope,identity) DO UPDATE SET paused=EXCLUDED.paused,reason=EXCLUDED.reason',**payload.model_dump())
        c.audit(db,user['uid'],'PAUSE_CHANGE',f'{payload.scope}:{payload.identity}',payload.reason)
        db.commit()
        return dict(paused=payload.paused)

    @router.post('/admin/api/attempts/{attempt_id}/containment/propose')
    def containment_propose(attempt_id: UUID,payload: Containment,user=Depends(admin),db=Depends(get_db)):
        c.lock(db)
        a=c.row(db,"SELECT * FROM payout_attempts WHERE id=:id AND phase='UNKNOWN' AND resolved_at IS NULL FOR UPDATE",id=attempt_id)
        if not a:
            c.fail(409,'Only unresolved UNKNOWN executions may be contained')
        old=c.row(db,'SELECT * FROM execution_containment_reviews WHERE attempt_id=:id',id=attempt_id)
        if old:
            if old['observed_minor']!=payload.observed_minor or old['evidence_ref']!=payload.evidence_ref:
                c.fail(409,'Containment evidence changed')
            return dict(review_id=str(old['id']))
        rid=uuid4()
        c.run(db,'INSERT INTO execution_containment_reviews(id,attempt_id,observed_minor,evidence_ref,proposer) VALUES(:id,:attempt,:observed,:evidence,:user)',id=rid,attempt=attempt_id,observed=payload.observed_minor,evidence=payload.evidence_ref,user=user['uid'])
        c.audit(db,user['uid'],'PROPOSE_PHYSICAL_CONTAINMENT',attempt_id,payload.evidence_ref)
        db.commit()
        return dict(review_id=str(rid))

    @router.post('/admin/api/containment/{review_id}/approve')
    def containment_approve(review_id: UUID,user=Depends(admin),db=Depends(get_db)):
        c.lock(db)
        r=c.row(db,'SELECT * FROM execution_containment_reviews WHERE id=:id FOR UPDATE',id=review_id)
        if not r:
            c.fail(404,'Containment review not found')
        if r['approved_at']:
            return dict(contained=True,financial_state='UNKNOWN')
        if r['proposer']==user['uid']:
            c.fail(409,'Independent physical containment reviewer required')
        a=c.row(db,"SELECT * FROM payout_attempts WHERE id=:id AND phase='UNKNOWN' AND resolved_at IS NULL FOR UPDATE",id=r['attempt_id'])
        if not a or c.row(db,'SELECT 1 FROM payout_attempts WHERE device_id=:device AND id<>:id AND resolved_at IS NULL AND execution_closed_at IS NULL',device=a['device_id'],id=a['id']):
            c.fail(409,'Current physical ownership must be reviewed')
        c.run(db,'UPDATE execution_containment_reviews SET approver=:user,approved_at=now() WHERE id=:id',user=user['uid'],id=review_id)
        c.run(db,'UPDATE payout_attempts SET execution_closed_at=now() WHERE id=:id',id=a['id'])
        c.run(db,'UPDATE payout_wallets SET observed_minor=:observed,observed_at=now(),enabled=true WHERE id=:id',observed=r['observed_minor'],id=a['wallet_id'])
        c.run(db,'UPDATE payout_devices SET quarantined=false WHERE id=:id',id=a['device_id'])
        c.audit(db,user['uid'],'APPROVE_PHYSICAL_CONTAINMENT',a['id'],r['evidence_ref'])
        db.commit()
        return dict(contained=True,financial_state='UNKNOWN')

    @router.post('/partner/api/key/rotate')
    def rotate(user=Depends(require_role('partner')),db=Depends(get_db)):
        from security import generate_api_key
        from config import get_settings
        if len(get_settings().api_key_verifier_secret.get_secret_value())<32:
            c.fail(409,'Configure API_KEY_VERIFIER_SECRET before migration to HMAC verifiers')
        partner=user['partner_id']
        if not partner:
            c.fail(403,'Partner user required')
        c.lock(db)
        key,prefix,verifier=generate_api_key()
        c.run(db,'UPDATE api_credentials SET revoked_at=now() WHERE partner_id=:id',id=partner)
        c.run(db,'UPDATE partners SET api_key_prefix=:prefix,api_key_hash=:hash WHERE id=:id',id=partner,prefix=prefix,hash=verifier)
        c.run(db,'INSERT INTO api_credentials(id,partner_id,prefix,verifier) VALUES(:id,:partner,:prefix,:verifier)',id=uuid4(),partner=partner,prefix=prefix,verifier=verifier)
        c.audit(db,user['uid'],'ROTATE_API_KEY',partner)
        db.commit()
        return dict(api_key=key,previous_keys_revoked=True)

    @router.get('/admin/api/payment-metrics')
    def metrics(user=Depends(admin),db=Depends(get_db)):
        states=c.run(db,'SELECT status,count(*) AS count,extract(epoch FROM now()-min(created_at)) AS oldest_age_seconds FROM payouts GROUP BY status').mappings().all()
        queue=c.row(db,"SELECT count(*) AS depth,extract(epoch FROM now()-min(created_at)) AS oldest_age_seconds FROM payout_queue WHERE status='PENDING'")
        deliveries=c.row(db,"SELECT count(*) AS outstanding,sum(attempts) AS attempts FROM payout_webhook_events WHERE state<>'DELIVERED'")
        ledger=c.run(db,'SELECT partner_id,currency,balance_minor,reserved_minor FROM ledger_accounts WHERE partner_id IS NOT NULL').mappings().all()
        return dict(payouts=[dict(r) for r in states],queue=dict(queue),webhooks=dict(deliveries),funding=[dict(r) for r in ledger])
    return router
