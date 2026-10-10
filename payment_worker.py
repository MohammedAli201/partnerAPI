"""Safe device contract on the EXISTING payout/queue tables. Simulator only."""
import hashlib
import hmac
import os
from datetime import datetime,timezone
from uuid import uuid4
import backend_core as c


def authenticate(db,token):
    if not token or len(token)<32:
        c.fail(401,'Independent worker credential required')
    worker=c.row(db,'SELECT * FROM payment_workers WHERE token_hash=:hash AND enabled',hash=hashlib.sha256(token.encode()).hexdigest())
    if not worker:
        c.fail(401,'Worker credential invalid')
    return worker


def gates(db,p,device,wallet):
    partner=c.row(db,'SELECT * FROM partners WHERE id=:id',id=p['partner_id'])
    if not partner['is_active'] or partner['paused'] or not partner['ledger_enabled']:
        c.fail(409,'Partner not eligible')
    if not device['enabled'] or device['quarantined'] or not wallet['enabled'] or wallet['currency']!=p['currency']:
        c.fail(409,'Device/wallet unavailable')
    if device['provider'].lower()!=p['provider'].lower() or device['network'].lower()!=c.stored_instructions(p)['network']:
        c.fail(409,'Device network/provider mismatch')
    for scope,identity in [('global','all'),('network',device['network']),('wallet',str(wallet['id']))]:
        if c.row(db,'SELECT 1 FROM payment_controls WHERE scope=:scope AND identity=:identity AND paused',scope=scope,identity=identity):
            c.fail(409,'Execution paused')
    if (datetime.now(timezone.utc)-wallet['observed_at']).total_seconds()>3600:
        c.fail(409,'Float observation stale')


def claim(db,worker,device_id):
    c.lock(db)
    device=c.row(db,'SELECT * FROM payout_devices WHERE id=:id AND worker_id=:worker FOR UPDATE',id=device_id,worker=worker['id'])
    if not device:
        c.fail(404,'Worker device not found')
    if c.row(db,'SELECT 1 FROM payout_attempts WHERE resolved_at IS NULL AND execution_closed_at IS NULL AND (device_id=:device OR wallet_id=:wallet)',device=device_id,wallet=device['wallet_id']):
        return None
    wallet=c.row(db,'SELECT * FROM payout_wallets WHERE id=:id FOR UPDATE',id=device['wallet_id'])
    if device['quarantined']:
        c.fail(409,'Device quarantined')
    job=c.row(db,'''SELECT q.* FROM payout_queue q JOIN payouts p ON p.id=q.payout_id JOIN partners partner ON partner.id=p.partner_id
        LEFT JOIN (SELECT old.partner_id,max(a.created_at) AS last_dispatch FROM payout_attempts a JOIN payouts old ON old.id=a.payout_id GROUP BY old.partner_id) dispatch ON dispatch.partner_id=p.partner_id
        WHERE q.status='PENDING' AND q.available_at<=now() AND p.status='RECEIVED' AND partner.ledger_enabled AND partner.is_active AND NOT partner.paused
        AND p.currency=:currency AND lower(p.provider)=lower(:provider)
        AND CASE WHEN p.canonical_hash IS NOT NULL THEN lower(p.request_payload::jsonb->>'payout_channel')=:network ELSE false END
        ORDER BY dispatch.last_dispatch ASC NULLS FIRST,q.created_at
        FOR UPDATE OF q SKIP LOCKED LIMIT 1''',currency=wallet['currency'],provider=device['provider'],network=device['network'].lower())
    if not job:
        return None
    p=c.row(db,'SELECT * FROM payouts WHERE id=:id FOR UPDATE',id=job['payout_id'])
    gates(db,p,device,wallet)
    if job['dispatch_count']>=5:
        c.run(db,"UPDATE payout_queue SET status='HELD' WHERE payout_id=:id",id=p['id'])
        c.audit(db,worker['id'],'RETRY_LIMIT_HOLD',p['id'])
        return None
    n=c.minor(p['amount'],p['currency'])
    asset=c.row(db,'UPDATE ledger_accounts SET reserved_minor=reserved_minor+:n WHERE id=:id AND balance_minor-reserved_minor>=:n RETURNING *',id=wallet['account_id'],n=n)
    if not asset or wallet['observed_minor']<asset['reserved_minor']:
        c.fail(402,'Wallet float insufficient')
    job=c.row(db,"UPDATE payout_queue SET status='IN_PROGRESS',worker_id=:worker,lease_until=now()+interval '120 seconds',generation=generation+1,dispatch_count=dispatch_count+1 WHERE payout_id=:id RETURNING *",id=p['id'],worker=str(worker['id']))
    aid=uuid4()
    command=dict(payout_id=str(p['id']),attempt_id=str(aid),device_id=str(device['id']),wallet_id=str(wallet['id']),lease_generation=job['generation'],
        instruction_hash=p['canonical_hash'] or c.digest(c.stored_instructions(p)),**{k:v for k,v in c.stored_instructions(p).items() if k not in ('version','reference')})
    c.run(db,'''INSERT INTO payout_attempts(id,payout_id,attempt_number,worker_id,device_id,wallet_id,generation,instructions,instruction_hash,phase)
        VALUES(:id,:payout,:number,:worker,:device,:wallet,:generation,CAST(:instructions AS jsonb),:hash,'CLAIMED')''',id=aid,payout=p['id'],number=job['dispatch_count'],worker=worker['id'],device=device['id'],wallet=wallet['id'],generation=job['generation'],instructions=c.canonical(command),hash=command['instruction_hash'])
    c.run(db,'INSERT INTO wallet_reservations(attempt_id,wallet_id,amount_minor) VALUES(:id,:wallet,:amount)',id=aid,wallet=wallet['id'],amount=n)
    c.change(db,p,'PROCESSING',worker['id'],'CLAIMED_NOT_ARMED')
    return command


def owned(db,worker,aid,generation,live=True):
    c.lock(db)
    a=c.row(db,'SELECT * FROM payout_attempts WHERE id=:id AND worker_id=:worker FOR UPDATE',id=aid,worker=worker['id'])
    if not a:
        c.fail(404,'Attempt not found')
    p=c.row(db,'SELECT * FROM payouts WHERE id=:id FOR UPDATE',id=a['payout_id'])
    job=c.row(db,'SELECT *,lease_until>now() AS live FROM payout_queue WHERE payout_id=:id FOR UPDATE',id=p['id'])
    if live and (not job or not job['live'] or job['generation']!=generation or a['generation']!=generation or a['resolved_at'] or a['phase']=='UNKNOWN' or job['worker_id']!=str(worker['id'])):
        c.fail(409,'Stale execution permission')
    return a,p,job


def arm(db,worker,aid,generation,hashed):
    a,p,job=owned(db,worker,aid,generation)
    if hashed!=a['instruction_hash']:
        c.fail(409,'Instructions changed')
    if a['phase']=='ARMED':
        return dict(armed=True,execute_again=False)
    if a['phase']!='CLAIMED':
        c.fail(409,'Cannot arm attempt')
    device=c.row(db,'SELECT * FROM payout_devices WHERE id=:id',id=a['device_id'])
    wallet=c.row(db,'SELECT * FROM payout_wallets WHERE id=:id',id=a['wallet_id'])
    gates(db,p,device,wallet)
    if not c.row(db,"SELECT 1 FROM payout_reservations WHERE payout_id=:id AND status='ACTIVE'",id=p['id']) or not c.row(db,"SELECT 1 FROM wallet_reservations WHERE attempt_id=:id AND state='ACTIVE'",id=aid):
        c.fail(409,'Required reservations missing')
    asset=c.row(db,'SELECT * FROM ledger_accounts WHERE id=:id',id=wallet['account_id'])
    if asset['balance_minor']<asset['reserved_minor'] or wallet['observed_minor']<asset['reserved_minor']:
        c.fail(402,'Wallet float no longer sufficient')
    c.run(db,"UPDATE payout_attempts SET phase='ARMED',armed_at=now() WHERE id=:id",id=aid)
    c.audit(db,worker['id'],'ARM_DURABLE',aid)
    return dict(armed=True,execute_again=False)


def heartbeat(db,worker,aid,generation):
    a,p,_=owned(db,worker,aid,generation)
    c.run(db,"UPDATE payout_queue SET lease_until=now()+interval '120 seconds' WHERE payout_id=:id",id=p['id'])
    c.run(db,'UPDATE payment_workers SET heartbeat_at=now() WHERE id=:id',id=worker['id'])
    return dict(phase=a['phase'])


def unknown(db,a,p,actor,reason):
    if p['status'] in ('SENT','FAILED','REJECTED','CANCELLED'):
        c.audit(db,actor,'LATE_EVIDENCE',p['id'],reason)
        return p
    if a['resolved_at'] is None:
        c.run(db,"UPDATE payout_attempts SET phase='UNKNOWN' WHERE id=:id",id=a['id'])
    else:
        # Preserve resolved attempt history. Freeze current ownership and the old
        # physical wallet if late evidence contradicts a pre-arm expiry.
        current=c.row(db,'SELECT * FROM payout_attempts WHERE payout_id=:id AND resolved_at IS NULL FOR UPDATE',id=p['id'])
        if current:
            c.run(db,"UPDATE payout_attempts SET phase='UNKNOWN' WHERE id=:id",id=current['id'])
            c.run(db,'UPDATE payout_devices SET quarantined=true WHERE id=:id',id=current['device_id'])
        c.run(db,'UPDATE payout_wallets SET enabled=false WHERE id=:id',id=a['wallet_id'])
    c.run(db,'UPDATE payout_devices SET quarantined=true WHERE id=:id',id=a['device_id'])
    c.run(db,"UPDATE payout_queue SET status='HELD' WHERE payout_id=:id",id=p['id'])
    c.run(db,'''INSERT INTO reconciliation_cases(id,payout_id,reason) VALUES(:id,:payout,:reason)
        ON CONFLICT(payout_id) WHERE resolved_at IS NULL DO NOTHING''',id=uuid4(),payout=p['id'],reason=reason)
    return c.change(db,p,'UNKNOWN',actor,reason)


def wallet_release(db,a,state):
    reservation=c.row(db,"SELECT * FROM wallet_reservations WHERE attempt_id=:id AND state='ACTIVE' FOR UPDATE",id=a['id'])
    if not reservation:
        c.fail(409,'Wallet reservation missing')
    wallet=c.row(db,'SELECT * FROM payout_wallets WHERE id=:id',id=a['wallet_id'])
    c.run(db,'UPDATE ledger_accounts SET reserved_minor=reserved_minor-:amount WHERE id=:id',id=wallet['account_id'],amount=reservation['amount_minor'])
    c.run(db,'UPDATE wallet_reservations SET state=:state WHERE attempt_id=:id',state=state,id=a['id'])
    return wallet


def paid(db,a,p,reference,evidence,actor):
    if p['status']=='SENT':
        return p
    if not reference:
        c.fail(422,'Verified receipt required')
    collision=c.row(db,'SELECT * FROM provider_receipts WHERE wallet_id=:wallet AND reference=:reference',wallet=a['wallet_id'],reference=reference)
    if collision:
        c.fail(409,'Receipt identity collision requires investigation')
    reservation,payable=c.release_partner(db,p,True)
    wallet=wallet_release(db,a,'CAPTURED')
    fee=c.minor(reservation['fee'],p['currency'])
    fees=c.account(db,f"fees:{p['currency']}",'FEES',p['currency'])
    amount=c.minor(p['amount'],p['currency'])
    entries=[(payable['id'],amount+fee),(wallet['account_id'],-amount)]
    if fee:
        entries.append((fees['id'],-fee))
    c.post(db,f"payout:{p['id']}",'PAYOUT',p['currency'],entries,evidence,p['id'])
    c.run(db,'INSERT INTO provider_receipts VALUES(:wallet,:reference,:payout,:evidence)',wallet=a['wallet_id'],reference=reference,payout=p['id'],evidence=evidence)
    c.run(db,"UPDATE payout_attempts SET phase='SUCCESS',resolved_at=now(),provider_reference=:reference,evidence_ref=:evidence WHERE id=:id",id=a['id'],reference=reference,evidence=evidence)
    if a.get('execution_closed_at') is None:
        c.run(db,'UPDATE payout_wallets SET observed_minor=GREATEST(0,observed_minor-:amount) WHERE id=:id',id=a['wallet_id'],amount=amount)
    # A contained UNKNOWN has already had independently observed physical float
    # recorded. Later financial recognition is not another physical debit.
    c.run(db,"UPDATE payout_queue SET status='DONE' WHERE payout_id=:id",id=p['id'])
    return c.change(db,p,'SENT',actor,'VERIFIED_PAYMENT')


def proof(command,reference,secret):
    return hmac.new(secret.encode(),c.canonical(dict(command=command,provider_reference=reference)).encode(),hashlib.sha256).hexdigest()


def result(db,worker,report):
    c.lock(db)
    hashed=c.digest(report)
    old=c.row(db,'SELECT * FROM worker_inbox WHERE worker_id=:worker AND event_id=:event',worker=worker['id'],event=report['event_id'])
    if old:
        if old['payload_hash']!=hashed:
            c.fail(409,'Result event content changed')
        return old['response']
    a,p,job=owned(db,worker,report['attempt_id'],report['lease_generation'],False)
    if a['instruction_hash']!=report['instruction_hash']:
        c.fail(409,'Result instructions changed')
    reference=report.get('provider_reference')
    evidence=report['evidence_ref']
    live=(job and job['live'] and a['generation']==job['generation']==report['lease_generation'] and a['resolved_at'] is None and a['phase']!='UNKNOWN')
    if p['status'] in ('SENT','FAILED','REJECTED','CANCELLED'):
        c.audit(db,worker['id'],'LATE_RESULT',p['id'],evidence)
        if report['outcome']=='SUCCESS' and reference!=a['provider_reference']:
            c.run(db,'''INSERT INTO reconciliation_cases(id,payout_id,reason) VALUES(:id,:payout,'POSSIBLE_EXTRA_DEBIT')
                ON CONFLICT(payout_id) WHERE resolved_at IS NULL DO NOTHING''',id=uuid4(),payout=p['id'])
            c.run(db,'UPDATE payout_devices SET quarantined=true WHERE id=:id',id=a['device_id'])
    elif a['resolved_at'] is not None and a['phase']=='NOT_SENT' and report['outcome']=='DEFINITE_FAILURE_BEFORE_SEND' and report['stage']=='BEFORE_ARM':
        c.audit(db,worker['id'],'LATE_PREARM_NONPAYMENT',p['id'],evidence)
    elif not live:
        p=unknown(db,a,p,worker['id'],'LATE_RESULT_RECONCILIATION')
    elif report['outcome']=='RETRYABLE_FAILURE_BEFORE_SEND' and report['stage']=='BEFORE_ARM' and a['phase']=='CLAIMED':
        wallet_release(db,a,'RELEASED')
        c.run(db,"UPDATE payout_attempts SET phase='NOT_SENT',resolved_at=now() WHERE id=:id",id=a['id'])
        c.run(db,"UPDATE payout_queue SET status='PENDING',generation=generation+1,worker_id=NULL,available_at=now()+interval '2 seconds' WHERE payout_id=:id",id=p['id'])
        p=c.change(db,p,'RECEIVED',worker['id'],'SAFE_PREARM_RETRY')
    elif report['outcome']=='DEFINITE_FAILURE_BEFORE_SEND' and report['stage']=='BEFORE_ARM' and a['phase']=='CLAIMED':
        c.release_partner(db,p)
        wallet_release(db,a,'RELEASED')
        c.run(db,"UPDATE payout_attempts SET phase='NOT_SENT',resolved_at=now() WHERE id=:id",id=a['id'])
        c.run(db,"UPDATE payout_queue SET status='DONE' WHERE payout_id=:id",id=p['id'])
        p=c.change(db,p,'FAILED',worker['id'],'NEVER_ARMED')
    else:
        secret=os.getenv('PAYOUT_SIMULATOR_SECRET','')
        verified=(os.getenv('PAYOUT_SIMULATOR_ENABLED')=='true' and worker['simulator'] and secret and report['outcome']=='SUCCESS' and a['phase']=='ARMED'
            and report['stage']=='AFTER_SEND' and reference and evidence.startswith('simulator://')
            and hmac.compare_digest(report.get('proof') or '',proof(a['instructions'],reference,secret)))
        if verified:
            p=paid(db,a,p,reference,evidence,worker['id'])
        else:
            p=unknown(db,a,p,worker['id'],'UNVERIFIED_OR_AMBIGUOUS')
    response=dict(ok=True,status=p['status'],payout_id=str(p['id']))
    c.run(db,'INSERT INTO worker_inbox VALUES(:worker,:event,:hash,CAST(:payload AS jsonb),CAST(:response AS jsonb),now())',worker=worker['id'],event=report['event_id'],hash=hashed,payload=c.canonical(report),response=c.canonical(response))
    return response


def reap(db):
    c.lock(db)
    jobs=c.run(db,"SELECT * FROM payout_queue WHERE status='IN_PROGRESS' AND lease_until<now() FOR UPDATE SKIP LOCKED LIMIT 50").mappings().all()
    for job in jobs:
        p=c.row(db,'SELECT * FROM payouts WHERE id=:id FOR UPDATE',id=job['payout_id'])
        a=c.row(db,'SELECT * FROM payout_attempts WHERE payout_id=:id AND resolved_at IS NULL FOR UPDATE',id=p['id'])
        if a and a['phase']=='CLAIMED':
            wallet_release(db,a,'RELEASED')
            c.run(db,"UPDATE payout_attempts SET phase='NOT_SENT',resolved_at=now() WHERE id=:id",id=a['id'])
            c.run(db,"UPDATE payout_queue SET status='PENDING',generation=generation+1,worker_id=NULL,available_at=now()+make_interval(secs=>:delay) WHERE payout_id=:id",id=p['id'],delay=min(300,2**job['dispatch_count'])+int.from_bytes(os.urandom(1),'big')%5)
            c.change(db,p,'RECEIVED','reaper','EXPIRED_BEFORE_ARM')
        elif a:
            unknown(db,a,p,'reaper','EXPIRED_AFTER_ARM')
        else:
            c.run(db,"UPDATE payout_queue SET status='HELD' WHERE payout_id=:id",id=p['id'])
            c.run(db,"INSERT INTO reconciliation_cases(id,payout_id,reason) VALUES(:id,:payout,'Legacy lease has no durable submission boundary') ON CONFLICT(payout_id) WHERE resolved_at IS NULL DO NOTHING",id=uuid4(),payout=p['id'])
            c.change(db,p,'UNKNOWN','reaper','LEGACY_UNKNOWN')
    return len(jobs)


def cancel(db,partner,pid):
    c.lock(db)
    p=c.row(db,'SELECT * FROM payouts WHERE id=:id AND partner_id=:partner FOR UPDATE',id=pid,partner=partner)
    if not p:
        c.fail(404,'Payout not found')
    if p['status']=='CANCELLED':
        return dict(status='CANCELLED')
    a=c.row(db,'SELECT * FROM payout_attempts WHERE payout_id=:id AND resolved_at IS NULL FOR UPDATE',id=pid)
    if p['status']!='RECEIVED' and not (p['status']=='PROCESSING' and a and a['phase']=='CLAIMED'):
        c.fail(409,'Cancellation unsafe after execution may have been submitted')
    if a:
        wallet_release(db,a,'RELEASED')
        c.run(db,"UPDATE payout_attempts SET phase='CANCELLED',resolved_at=now() WHERE id=:id",id=a['id'])
    c.release_partner(db,p)
    c.run(db,"UPDATE payout_queue SET status='DONE',generation=generation+1,lease_until=now() WHERE payout_id=:id",id=pid)
    p=c.change(db,p,'CANCELLED',partner,'CANCELLED_BEFORE_ARM')
    return dict(status=p['status'])
