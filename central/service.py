"""Short, committed transactions only. No phone or webhook I/O here."""
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def run(db, sql, **params):
    return db.execute(text(sql), params)


def row(db, sql, **params):
    return run(db, sql, **params).mappings().first()


def fail(code, detail):
    raise HTTPException(code, detail)


def money_lock(db):
    # Deliberate initial serialization of SHORT financial transactions.
    # This is a DB lock, never permission to repeat a physical payment.
    run(db, 'SELECT pg_advisory_xact_lock(610092026)')


def audit(db, actor, action, target, evidence='none'):
    run(db, '''INSERT INTO central.audit(id,actor,action,target,evidence_ref,correlation_id)
               VALUES(:id,:actor,:action,:target,:evidence,:correlation)''',
        id=uuid4(), actor=str(actor), action=action, target=str(target), evidence=evidence, correlation=uuid4())


def account(db, key, kind, currency, partner=None, spendable=False):
    run(db, '''INSERT INTO central.accounts(id,business_key,kind,currency,partner_id,spendable)
               VALUES(:id,:key,:kind,:currency,:partner,:spendable) ON CONFLICT(business_key) DO NOTHING''',
        id=uuid4(), key=key, kind=kind, currency=currency, partner=partner, spendable=spendable)
    result = row(db, 'SELECT * FROM central.accounts WHERE business_key=:key FOR UPDATE', key=key)
    if result['currency'] != currency or result['kind'] != kind or result['partner_id'] != partner:
        fail(409, 'Account identity conflict')
    return result


def partner_account(db, partner, currency):
    return account(db, f'partner:{partner}:{currency}', 'PARTNER_PAYABLE', currency, partner, True)


def post(db, key, event, entries, evidence, payout=None):
    """Positive entries are debits, negative entries credits; one currency per journal.

    Spendable cached balances use each account's normal side (customer payable
    is credit normal; wallet assets are debit normal).
    """
    if not evidence or len(entries) < 2 or sum(amount for _, amount in entries) != 0:
        fail(422, 'Posting requires balanced entries and evidence')
    existing = row(db, 'SELECT * FROM central.journals WHERE business_event_key=:key', key=key)
    if existing:
        stored = run(db, 'SELECT account_id,amount_minor FROM central.entries WHERE journal_id=:id ORDER BY account_id,amount_minor', id=existing['id']).all()
        expected = sorted(entries, key=lambda item: (str(item[0]), item[1]))
        if [(str(a), n) for a, n in stored] != [(str(a), n) for a, n in expected] or existing['event_type'] != event or existing['evidence_ref'] != evidence or existing['payout_id'] != payout:
            fail(409, 'Journal business key reused with different effects')
        return existing['id']
    accounts = []
    for aid in sorted({aid for aid, _ in entries}, key=str):
        accounts.append(row(db, 'SELECT * FROM central.accounts WHERE id=:id FOR UPDATE', id=aid))
    if None in accounts or len({a['currency'] for a in accounts}) != 1:
        fail(422, 'Posting must use existing accounts of one currency')
    jid = uuid4()
    run(db, '''INSERT INTO central.journals(id,business_event_key,event_type,payout_id,evidence_ref)
               VALUES(:id,:key,:event,:payout,:evidence)''', id=jid,key=key,event=event,payout=payout,evidence=evidence)
    currency = accounts[0]['currency']
    for aid, amount in entries:
        if not isinstance(amount, int) or amount == 0:
            fail(422, 'Nonzero integer minor units required')
        run(db, 'INSERT INTO central.entries VALUES(:id,:journal,:account,:currency,:amount)',
            id=uuid4(),journal=jid,account=aid,currency=currency,amount=amount)
    return jid


def reserve(db, p, kind, aid, amount):
    changed = row(db, '''UPDATE central.accounts SET reserved_minor=reserved_minor+:amount
        WHERE id=:id AND spendable AND balance_minor-reserved_minor>=:amount RETURNING id''', id=aid,amount=amount)
    if not changed:
        fail(402, f'Insufficient {kind.lower()} funding')
    run(db, '''INSERT INTO central.reservations(id,payout_id,partner_id,currency,kind,account_id,amount_minor)
               VALUES(:id,:payout,:partner,:currency,:kind,:account,:amount)''',
        id=uuid4(),payout=p['id'],partner=p['partner_id'],currency=p['currency'],kind=kind,account=aid,amount=amount)


def release(db, payout, capture=False):
    reservations = run(db, "SELECT * FROM central.reservations WHERE payout_id=:id AND state='ACTIVE' FOR UPDATE", id=payout).mappings().all()
    for reservation in reservations:
        run(db, 'UPDATE central.accounts SET reserved_minor=reserved_minor-:amount WHERE id=:id',
            amount=reservation['amount_minor'],id=reservation['account_id'])
        run(db, 'UPDATE central.reservations SET state=:state,resolved_at=now() WHERE id=:id',
            state='CAPTURED' if capture else 'RELEASED',id=reservation['id'])


def event(db, p, old, actor, reason):
    eid = uuid4()
    run(db, '''INSERT INTO central.history(id,payout_id,status_version,old_status,new_status,actor,reason)
        VALUES(:id,:payout,:version,:old,:new,:actor,:reason)''',
        id=uuid4(),payout=p['id'],version=p['status_version'],old=old,new=p['status'],actor=str(actor),reason=reason)
    payload = dict(event_id=str(eid),payout_id=str(p['id']),external_reference=p['external_reference'],
                   status=p['status'],status_version=p['status_version'],timestamp=datetime.now(timezone.utc).isoformat())
    run(db, '''INSERT INTO central.outbox(id,partner_id,payout_id,status_version,event_type,payload)
        VALUES(:id,:partner,:payout,:version,'payout.status',CAST(:payload AS jsonb))''',
        id=eid,partner=p['partner_id'],payout=p['id'],version=p['status_version'],payload=canonical(payload))
    partner = row(db, 'SELECT * FROM central.partners WHERE id=:id', id=p['partner_id'])
    if partner['webhook_url'] and partner['webhook_secret']:
        run(db, '''INSERT INTO central.deliveries(event_id,destination_version,destination_url,signing_secret)
            VALUES(:id,:version,:url,:secret)''',id=eid,version=partner['destination_version'],
            url=partner['webhook_url'],secret=partner['webhook_secret'])


def transition(db, p, state, actor, reason):
    if p['status'] == state:
        return p
    if p['status'] in ('PAID','FAILED','CANCELLED'):
        fail(409, 'Final payout cannot be overwritten')
    changed = row(db, '''UPDATE central.payouts SET status=:status,status_version=status_version+1,
        hold_reason=:reason,updated_at=now() WHERE id=:id RETURNING *''',
        id=p['id'],status=state,reason=reason if state in ('UNKNOWN','ON_HOLD') else None)
    event(db, changed, p['status'], actor, reason)
    return changed


def gates(db, p, device=None, wallet=None):
    partner = row(db, 'SELECT * FROM central.partners WHERE id=:id', id=p['partner_id'])
    if partner['paused'] or p['corridor'] not in partner['corridors']:
        fail(409, 'Partner paused or corridor unavailable')
    scopes = [('global','all'),('network',p['network'])]
    if wallet:
        scopes.append(('wallet',str(wallet['id'])))
        if not wallet['enabled'] or wallet['currency'] != p['currency'] or p['amount_minor']>wallet['max_payout_minor']:
            fail(409, 'Wallet not eligible')
        if not wallet['observed_at'] or (datetime.now(timezone.utc)-wallet['observed_at']).total_seconds()>3600:
            fail(409, 'Wallet balance observation stale')
        reserved = row(db, 'SELECT reserved_minor FROM central.accounts WHERE id=:id', id=wallet['account_id'])['reserved_minor']
        if wallet['observed_minor'] is None or wallet['observed_minor'] < reserved:
            fail(409, 'Observed wallet float below reservations')
        used = row(db, '''SELECT COALESCE(sum(p.amount_minor),0) AS n FROM central.attempts a
            JOIN central.payouts p ON p.id=a.payout_id WHERE a.wallet_id=:id
            AND a.armed_at>=date_trunc('day',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
            AND a.phase<>'NOT_SENT' ''', id=wallet['id'])['n']
        if used+p['amount_minor']>wallet['daily_limit_minor']:
            fail(409, 'Wallet daily limit reached')
    if device and (not device['enabled'] or device['quarantined'] or p['network'] not in device['networks']):
        fail(409, 'Device not eligible')
    for scope, identity in scopes:
        if row(db, 'SELECT 1 FROM central.controls WHERE scope=:scope AND identity=:identity AND paused', scope=scope,identity=identity):
            fail(409, 'Execution paused')


def admit(db, partner, key, instructions):
    money_lock(db)
    request_hash = digest(dict(version=1, **instructions))
    existing = row(db, "SELECT * FROM central.api_idempotency WHERE partner_id=:partner AND operation='CREATE' AND idempotency_key=:key",partner=partner,key=key)
    if existing:
        if existing['request_hash'] != request_hash:
            fail(409, 'Idempotency key instructions changed')
        return existing['response']
    config = row(db, 'SELECT * FROM central.partners WHERE id=:id', id=partner)
    if config['paused'] or instructions['corridor'] not in config['corridors']:
        fail(409, 'Partner paused or unsupported corridor')
    payout = row(db, '''INSERT INTO central.payouts(id,partner_id,external_reference,canonical_hash,amount_minor,
        fee_minor,currency,recipient,network,corridor,status)
        VALUES(:id,:partner,:external_reference,:hash,:amount_minor,:fee,:currency,:recipient,:network,:corridor,'QUEUED')
        ON CONFLICT(partner_id,external_reference) DO NOTHING RETURNING *''',
        id=uuid4(),partner=partner,hash=request_hash,fee=config['fee_minor'],**instructions)
    if not payout:
        payout = row(db, 'SELECT * FROM central.payouts WHERE partner_id=:partner AND external_reference=:reference',partner=partner,reference=instructions['external_reference'])
        if payout['canonical_hash'] != request_hash:
            fail(409, 'External reference instructions changed')
        # Replay original admission even after the live payout has completed.
        response = row(db, 'SELECT response FROM central.api_idempotency WHERE payout_id=:id ORDER BY created_at LIMIT 1',id=payout['id'])['response']
    else:
        funding = partner_account(db, partner, payout['currency'])
        reserve(db,payout,'PARTNER',funding['id'],payout['amount_minor']+payout['fee_minor'])
        run(db, "INSERT INTO central.jobs(payout_id,state) VALUES(:id,'READY')",id=payout['id'])
        event(db,payout,None,partner,'ADMITTED')
        response = dict(payout_id=str(payout['id']),external_reference=payout['external_reference'],status='QUEUED',status_url=f"/v1/payouts/{payout['id']}")
    run(db, '''INSERT INTO central.api_idempotency(partner_id,operation,idempotency_key,request_hash,payout_id,response)
        VALUES(:partner,'CREATE',:key,:hash,:payout,CAST(:response AS jsonb))''',partner=partner,key=key,hash=request_hash,payout=payout['id'],response=canonical(response))
    return response


def get_payout(db, pid, partner=None):
    p = row(db, 'SELECT * FROM central.payouts WHERE id=:id' + (' AND partner_id=:partner' if partner else '') + ' FOR UPDATE',id=pid,partner=partner)
    if not p:
        fail(404, 'Payout not found')
    return p


def claim(db, worker, device_id):
    money_lock(db)
    device = row(db, 'SELECT * FROM central.devices WHERE id=:id AND worker_id=:worker FOR UPDATE',id=device_id,worker=worker)
    w = row(db, 'SELECT * FROM central.workers WHERE id=:id AND enabled FOR UPDATE',id=worker)
    if not device or not w or device['quarantined'] or not device['enabled']:
        fail(409, 'Worker/device unavailable')
    run(db, 'UPDATE central.workers SET heartbeat_at=now() WHERE id=:id',id=worker)
    if row(db, 'SELECT 1 FROM central.attempts WHERE (device_id=:device OR wallet_id=:wallet) AND resolved_at IS NULL',device=device_id,wallet=device['wallet_id']):
        return None
    wallet = row(db, 'SELECT * FROM central.wallets WHERE id=:id FOR UPDATE',id=device['wallet_id'])
    # Fairness: prefer partner with oldest last dispatch, then FIFO. Only one phone claim.
    job = row(db, '''SELECT j.* FROM central.jobs j JOIN central.payouts p ON p.id=j.payout_id
        JOIN central.partners partner ON partner.id=p.partner_id
        WHERE j.state='READY' AND j.available_at<=now() AND p.status='QUEUED' AND NOT partner.paused
          AND p.currency=:currency AND p.network=ANY(:networks) AND p.amount_minor<=:maximum
        ORDER BY (SELECT max(a.created_at) FROM central.attempts a JOIN central.payouts other ON other.id=a.payout_id
                  WHERE other.partner_id=p.partner_id) ASC NULLS FIRST,j.priority DESC,j.created_at
        FOR UPDATE OF j SKIP LOCKED LIMIT 1''',currency=wallet['currency'],networks=device['networks'],maximum=wallet['max_payout_minor'])
    if not job:
        return None
    p = get_payout(db, job['payout_id'])
    gates(db,p,device,wallet)
    if job['dispatch_count']>=5:
        transition(db,p,'ON_HOLD',worker,'RETRY_LIMIT')
        run(db,"UPDATE central.jobs SET state='HELD' WHERE payout_id=:id",id=p['id'])
        return None
    reserve(db,p,'WALLET',wallet['account_id'],p['amount_minor'])
    job = row(db, '''UPDATE central.jobs SET state='LEASED',lease_owner=:worker,lease_until=now()+interval '120 seconds',
        generation=generation+1,dispatch_count=dispatch_count+1 WHERE payout_id=:id RETURNING *''',worker=worker,id=p['id'])
    aid = uuid4()
    instructions = {k:p[k] for k in ('amount_minor','currency','recipient','network','corridor')}
    command = dict(payout_id=str(p['id']),attempt_id=str(aid),device_id=str(device_id),wallet_id=str(wallet['id']),
                   lease_generation=job['generation'],instruction_hash=p['canonical_hash'],**instructions)
    run(db, '''INSERT INTO central.attempts(id,payout_id,attempt_number,worker_id,device_id,wallet_id,generation,instruction_hash,instructions,phase)
        VALUES(:id,:payout,:number,:worker,:device,:wallet,:generation,:hash,CAST(:instructions AS jsonb),'CLAIMED')''',
        id=aid,payout=p['id'],number=job['dispatch_count'],worker=worker,device=device_id,wallet=wallet['id'],generation=job['generation'],hash=p['canonical_hash'],instructions=canonical(command))
    transition(db,p,'CLAIMED',worker,'CLAIMED')
    return command


def owned(db, worker, aid, generation, require_live=True):
    a = row(db,'SELECT * FROM central.attempts WHERE id=:id AND worker_id=:worker FOR UPDATE',id=aid,worker=worker)
    if not a:
        fail(404,'Attempt not found')
    p = get_payout(db,a['payout_id'])
    job = row(db,'SELECT *,lease_until>now() AS live FROM central.jobs WHERE payout_id=:id FOR UPDATE',id=p['id'])
    if require_live and (a['generation']!=generation or job['generation']!=generation or job['lease_owner']!=worker or not job['live'] or a['resolved_at'] or a['phase']=='UNKNOWN'):
        fail(409,'Stale or resolved execution permission')
    return a,p,job


def heartbeat(db, worker, aid, generation):
    money_lock(db)
    a,p,j = owned(db,worker,aid,generation)
    run(db,"UPDATE central.jobs SET lease_until=now()+interval '120 seconds' WHERE payout_id=:id",id=p['id'])
    run(db,'UPDATE central.workers SET heartbeat_at=now() WHERE id=:id',id=worker)
    return dict(phase=a['phase'],lease_generation=generation)


def arm(db, worker, aid, generation, instruction_hash):
    money_lock(db)
    a,p,j = owned(db,worker,aid,generation)
    if a['instruction_hash']!=instruction_hash:
        fail(409,'Instruction hash changed')
    if a['phase']=='ARMED':
        return dict(armed=True,execute_again=False,attempt_id=str(aid))
    if a['phase']!='CLAIMED' or p['status']!='CLAIMED':
        fail(409,'Cannot arm this attempt')
    device = row(db,'SELECT * FROM central.devices WHERE id=:id FOR UPDATE',id=a['device_id'])
    wallet = row(db,'SELECT * FROM central.wallets WHERE id=:id FOR UPDATE',id=a['wallet_id'])
    worker_config = row(db,'SELECT * FROM central.workers WHERE id=:id',id=worker)
    if not worker_config['enabled']:
        fail(409,'Worker disabled')
    gates(db,p,device,wallet)
    reservations = run(db,"SELECT kind FROM central.reservations WHERE payout_id=:id AND state='ACTIVE'",id=p['id']).scalars().all()
    if set(reservations)!={'PARTNER','WALLET'}:
        fail(409,'Reservations missing')
    run(db,"UPDATE central.attempts SET phase='ARMED',armed_at=now() WHERE id=:id",id=aid)
    transition(db,p,'ARMED',worker,'PERMISSION_DURABLY_RECORDED')
    return dict(armed=True,execute_again=False,attempt_id=str(aid))


def unknown(db, a, p, actor, reason):
    if p['status'] in ('PAID','FAILED','CANCELLED'):
        audit(db,actor,'LATE_EVIDENCE',p['id'],reason)
        return p
    run(db,"UPDATE central.attempts SET phase='UNKNOWN' WHERE id=:id",id=a['id'])
    run(db,'UPDATE central.devices SET quarantined=true WHERE id=:id',id=a['device_id'])
    run(db,"UPDATE central.jobs SET state='HELD' WHERE payout_id=:id",id=p['id'])
    run(db,'''INSERT INTO central.cases(id,payout_id,reason) VALUES(:id,:payout,:reason)
        ON CONFLICT(payout_id) WHERE state<>'RESOLVED' DO NOTHING''',id=uuid4(),payout=p['id'],reason=reason)
    return transition(db,p,'UNKNOWN',actor,reason)


def settle_paid(db, a, p, reference, evidence, actor):
    if p['status']=='PAID':
        return p
    collision = row(db,'SELECT * FROM central.receipts WHERE wallet_id=:wallet AND provider_reference=:reference',wallet=a['wallet_id'],reference=reference)
    if collision and collision['payout_id']!=p['id']:
        return unknown(db,a,p,actor,'RECEIPT_IDENTITY_COLLISION')
    statement=row(db,'SELECT * FROM central.statement_items WHERE wallet_id=:wallet AND operator_reference=:reference',wallet=a['wallet_id'],reference=reference)
    if statement and (statement['amount_minor']!=-p['amount_minor'] or statement['recipient']!=p['recipient'] or statement['currency']!=p['currency'] or statement['payout_id'] not in (None,p['id'])):
        fail(409,'Statement evidence contradicts payment')
    partner = partner_account(db,p['partner_id'],p['currency'])
    wallet = row(db,'SELECT * FROM central.wallets WHERE id=:id',id=a['wallet_id'])
    fees = account(db,f"fees:{p['currency']}",'FEES',p['currency'])
    release(db,p['id'],True)
    if statement and statement['payout_id'] is None:
        suspense=account(db,f"suspense:{p['currency']}",'SUSPENSE',p['currency'])
        # An unmatched debit was already recorded as real loss/suspense. Reclassify
        # that posting before recognizing the confirmed payout, without a second debit.
        post(db,f"statement-reclassify:{statement['id']}",'RECLASSIFY',
             [(wallet['account_id'],p['amount_minor']),(suspense['id'],-p['amount_minor'])],evidence,p['id'])
    if statement:
        run(db,'UPDATE central.statement_items SET payout_id=:payout WHERE id=:id',id=statement['id'],payout=p['id'])
    entries=[(partner['id'],p['amount_minor']+p['fee_minor']), (wallet['account_id'],-p['amount_minor'])]
    if p['fee_minor']:
        entries += [(fees['id'],-p['fee_minor'])]
    post(db,f"payout:{p['id']}",'PAYOUT',entries,evidence,p['id'])
    run(db,'INSERT INTO central.receipts VALUES(:wallet,:reference,:payout,:evidence)',wallet=a['wallet_id'],reference=reference,payout=p['id'],evidence=evidence)
    run(db,"UPDATE central.attempts SET phase='SUCCEEDED',resolved_at=now(),provider_reference=:reference,evidence_ref=:evidence WHERE id=:id",id=a['id'],reference=reference,evidence=evidence)
    run(db,"UPDATE central.jobs SET state='DONE' WHERE payout_id=:id",id=p['id'])
    # Observation becomes conservatively lower; reconcile actual fees from operator statements.
    run(db,'UPDATE central.wallets SET observed_minor=observed_minor-:amount WHERE id=:id',id=a['wallet_id'],amount=p['amount_minor'])
    return transition(db,p,'PAID',actor,'VERIFIED_PAYMENT')


def simulator_proof(command, reference, secret):
    return hmac.new(secret.encode(),canonical(dict(command=command,provider_reference=reference)).encode(),hashlib.sha256).hexdigest()


def result(db, worker, report):
    money_lock(db)
    payload_hash=digest(report)
    existing=row(db,"SELECT * FROM central.inbox WHERE source_type='worker' AND source_id=:worker AND event_id=:event",worker=worker,event=report['event_id'])
    if existing:
        if existing['payload_hash']!=payload_hash:
            fail(409,'Event ID reused with changed payload')
        return existing['response']
    a,p,j=owned(db,worker,report['attempt_id'],report['lease_generation'],False)
    if report['instruction_hash']!=a['instruction_hash']:
        fail(409,'Result instructions changed')
    evidence=report['evidence_ref']
    if a['resolved_at'] is None:
        run(db,'''UPDATE central.attempts SET evidence_ref=:evidence,
            provider_reference=COALESCE(provider_reference,:reference),
            may_have_submitted_at=CASE WHEN :stage='AFTER_SEND' THEN COALESCE(may_have_submitted_at,CAST(:occurred AS timestamptz)) ELSE may_have_submitted_at END
            WHERE id=:id''',id=a['id'],evidence=evidence,reference=report['provider_reference'],stage=report['stage'],occurred=report['occurred_at'])
    is_current=(j['generation']==report['lease_generation']==a['generation'] and j['live'] and a['resolved_at'] is None and a['phase']!='UNKNOWN')
    if p['status'] in ('PAID','FAILED','CANCELLED'):
        audit(db,worker,'LATE_RESULT',p['id'],evidence)
        # Possible debit after cancellation/non-payment resolution must open an incident.
        different_paid_receipt=(p['status']=='PAID' and report['outcome']=='SUCCESS' and
                               report['provider_reference'] and report['provider_reference']!=a['provider_reference'])
        if different_paid_receipt or (p['status']!='PAID' and report['outcome']!='DEFINITE_FAILURE_BEFORE_SEND'):
            run(db,'''INSERT INTO central.cases(id,payout_id,reason) VALUES(:id,:payout,'POSSIBLE_DEBIT_AFTER_FINALIZATION')
                ON CONFLICT(payout_id) WHERE state<>'RESOLVED' DO NOTHING''',id=uuid4(),payout=p['id'])
            run(db,'UPDATE central.devices SET quarantined=true WHERE id=:id',id=a['device_id'])
    elif not is_current:
        p=unknown(db,a,p,worker,'LATE_RESULT_REQUIRES_RECONCILIATION')
        audit(db,worker,'LATE_RESULT',p['id'],evidence)
    elif report['outcome']=='DEFINITE_FAILURE_BEFORE_SEND' and a['phase']=='CLAIMED' and report['stage']=='BEFORE_ARM':
        release(db,p['id'])
        run(db,"UPDATE central.attempts SET phase='NOT_SENT',resolved_at=now(),evidence_ref=:evidence WHERE id=:id",id=a['id'],evidence=evidence)
        run(db,"UPDATE central.jobs SET state='DONE' WHERE payout_id=:id",id=p['id'])
        p=transition(db,p,'FAILED',worker,'PROVEN_NOT_ARMED')
    else:
        worker_config=row(db,'SELECT * FROM central.workers WHERE id=:id',id=worker)
        secret=os.getenv('CENTRAL_SIMULATOR_SECRET','')
        verified=(os.getenv('CENTRAL_SIMULATOR_ENABLED')=='true' and secret and worker_config['simulator']
            and report['outcome']=='SUCCESS' and a['phase']=='ARMED' and report['stage']=='AFTER_SEND'
            and report['provider_reference'] and report['evidence_ref'].startswith('simulator://')
            and hmac.compare_digest(report['proof'] or '',simulator_proof(a['instructions'],report['provider_reference'],secret)))
        if verified:
            p=settle_paid(db,a,p,report['provider_reference'],evidence,worker)
        else:
            p=unknown(db,a,p,worker,'UNVERIFIED_OR_AMBIGUOUS_RESULT')
    response=dict(accepted=True,payout_id=str(p['id']),status=p['status'])
    run(db,'''INSERT INTO central.inbox(id,source_type,source_id,event_id,payload_hash,evidence_ref,protected_payload,processing_state,response)
        VALUES(:id,'worker',:worker,:event,:hash,:evidence,CAST(:payload AS jsonb),'PROCESSED',CAST(:response AS jsonb))''',
        id=uuid4(),worker=worker,event=report['event_id'],hash=payload_hash,evidence=evidence,payload=canonical(report),response=canonical(response))
    return response


def cancel(db, partner, pid):
    money_lock(db)
    p=get_payout(db,pid,partner)
    if p['status']=='CANCELLED':
        return dict(status='CANCELLED')
    if p['status'] not in ('QUEUED','CLAIMED','ON_HOLD'):
        fail(409,'Cancellation requires confirmed pre-arm state')
    a=row(db,'SELECT * FROM central.attempts WHERE payout_id=:id AND resolved_at IS NULL FOR UPDATE',id=pid)
    if a and a['phase']!='CLAIMED':
        fail(409,'Attempt might have submitted')
    if a:
        run(db,"UPDATE central.attempts SET phase='CANCELLED',resolved_at=now() WHERE id=:id",id=a['id'])
    run(db,"UPDATE central.jobs SET state='DONE',generation=generation+1,lease_until=now() WHERE payout_id=:id",id=pid)
    release(db,pid)
    p=transition(db,p,'CANCELLED',partner,'CANCELLED_BEFORE_ARM')
    return dict(status=p['status'])


def reap(db):
    money_lock(db)
    jobs=run(db,"SELECT * FROM central.jobs WHERE state='LEASED' AND lease_until<now() FOR UPDATE SKIP LOCKED LIMIT 50").mappings().all()
    for j in jobs:
        p=get_payout(db,j['payout_id'])
        a=row(db,'SELECT * FROM central.attempts WHERE payout_id=:id AND resolved_at IS NULL FOR UPDATE',id=p['id'])
        if not a:
            fail(409,'Leased job missing unresolved attempt')
        if a['phase']=='CLAIMED':
            run(db,"UPDATE central.attempts SET phase='NOT_SENT',resolved_at=now() WHERE id=:id",id=a['id'])
            # Only wallet reservation released; keep partner funding across safe retry.
            r=row(db,"SELECT * FROM central.reservations WHERE payout_id=:id AND kind='WALLET' AND state='ACTIVE' FOR UPDATE",id=p['id'])
            if r:
                run(db,'UPDATE central.accounts SET reserved_minor=reserved_minor-:amount WHERE id=:id',id=r['account_id'],amount=r['amount_minor'])
                run(db,"UPDATE central.reservations SET state='RELEASED',resolved_at=now() WHERE id=:id",id=r['id'])
            run(db,"UPDATE central.jobs SET state='READY',generation=generation+1,lease_owner=NULL,available_at=now()+make_interval(secs=>:delay) WHERE payout_id=:id",id=p['id'],delay=min(300,2**j['dispatch_count'])+int.from_bytes(os.urandom(1),'big')%5)
            transition(db,p,'QUEUED','reaper','EXPIRED_BEFORE_ARM')
        else:
            unknown(db,a,p,'reaper','EXPIRED_AFTER_ARM')
    return len(jobs)


def propose(db, reviewer, case_id, decision, evidence, reference, neutralized):
    money_lock(db)
    case=row(db,'SELECT * FROM central.cases WHERE id=:id FOR UPDATE',id=case_id)
    if not case or case['state']=='RESOLVED':
        fail(409,'Case unavailable')
    if decision=='PAID' and not reference:
        fail(422,'Verified operator reference required')
    if not neutralized:
        fail(422,'Stale execution must be neutralized before resolution')
    run(db,"UPDATE central.cases SET state='PROPOSED',decision=:decision,evidence_ref=:evidence,provider_reference=:reference,proposer=:reviewer,stale_execution_neutralized=:neutralized WHERE id=:id",
        id=case_id,decision=decision,evidence=evidence,reference=reference,reviewer=reviewer,neutralized=neutralized)
    audit(db,reviewer,'PROPOSE_RESOLUTION',case_id,evidence)
    return dict(state='PROPOSED')


def approve(db, reviewer, case_id):
    money_lock(db)
    case=row(db,'SELECT * FROM central.cases WHERE id=:id FOR UPDATE',id=case_id)
    if not case:
        fail(404,'Case not found')
    if case['state']=='RESOLVED':
        return dict(state='RESOLVED')
    if case['state']!='PROPOSED' or case['proposer']==reviewer:
        fail(409,'Independent reviewer required')
    p=get_payout(db,case['payout_id'])
    if p['status']!='UNKNOWN':
        fail(409,'Only UNKNOWN cases resolve through this path')
    a=row(db,'SELECT * FROM central.attempts WHERE payout_id=:id AND resolved_at IS NULL',id=p['id'])
    if case['decision']=='PAID':
        p=settle_paid(db,a,p,case['provider_reference'],case['evidence_ref'],reviewer)
        if p['status']!='PAID':
            fail(409,'Receipt collision requires investigation')
    else:
        if row(db,'''SELECT 1 FROM central.statement_items WHERE payout_id=:payout OR
            (wallet_id=:wallet AND operator_reference=:reference AND amount_minor=:amount AND recipient=:recipient)''',
            payout=p['id'],wallet=a['wallet_id'],reference=a['provider_reference'],amount=-p['amount_minor'],recipient=p['recipient']):
            fail(409,'Recorded operator debit contradicts non-payment resolution')
        release(db,p['id'])
        run(db,"UPDATE central.attempts SET phase='NOT_SENT',resolved_at=now(),evidence_ref=:evidence WHERE id=:id",id=a['id'],evidence=case['evidence_ref'])
        run(db,"UPDATE central.jobs SET state='DONE' WHERE payout_id=:id",id=p['id'])
        transition(db,p,'FAILED',reviewer,'INDEPENDENTLY_VERIFIED_NON_PAYMENT')
    run(db,"UPDATE central.cases SET state='RESOLVED',approver=:reviewer,resolved_at=now() WHERE id=:id",reviewer=reviewer,id=case_id)
    # Quarantine is deliberately retained until a separate idle inspection.
    audit(db,reviewer,'APPROVE_RESOLUTION',case_id,case['evidence_ref'])
    return dict(state='RESOLVED')


def funding(db, actor, kind, identity, currency, amount, reference, evidence):
    money_lock(db)
    bank=account(db,f'bank:{currency}','BANK',currency,spendable=True)
    if kind=='PARTNER':
        if not row(db,'SELECT 1 FROM central.partners WHERE id=:id',id=identity):
            fail(404,'Partner not found')
        target=partner_account(db,identity,currency)
        entries=[(bank['id'],amount),(target['id'],-amount)]
    else:
        wallet=row(db,'SELECT * FROM central.wallets WHERE id=:id AND currency=:currency',id=identity,currency=currency)
        if not wallet:
            fail(404,'Wallet not found')
        target=row(db,'SELECT * FROM central.accounts WHERE id=:id FOR UPDATE',id=wallet['account_id'])
        existing=row(db,'SELECT 1 FROM central.journals WHERE business_event_key=:key',key=f'funding:{kind}:{identity}:{reference}')
        if not existing and bank['balance_minor']-bank['reserved_minor']<amount:
            fail(402,'Bank liquidity insufficient for topup')
        entries=[(target['id'],amount),(bank['id'],-amount)]
    jid=post(db,f'funding:{kind}:{identity}:{reference}','PREFUND' if kind=='PARTNER' else 'TOPUP',entries,evidence)
    audit(db,actor,'CONFIRMED_FUNDING',jid,evidence)
    # Observed wallet balance is refreshed separately from an authoritative snapshot.
    return dict(journal_id=str(jid))


def import_statement(db, actor, wallet_id, source, evidence, items):
    """Record operator evidence once; no auto resolution from missing lines.

    debit items use negative signed amount. Unmatched movement posts suspense,
    unless it correlates to an unresolved attempt: then retain for two reviewers.
    """
    money_lock(db)
    payload_hash=digest(items)
    existing=row(db,'SELECT * FROM central.statement_imports WHERE wallet_id=:wallet AND source_reference=:source',wallet=wallet_id,source=source)
    if existing:
        if existing['payload_hash']!=payload_hash or existing['evidence_ref']!=evidence:
            fail(409,'Statement import identity reused')
        return dict(import_id=str(existing['id']))
    wallet=row(db,'SELECT * FROM central.wallets WHERE id=:id FOR UPDATE',id=wallet_id)
    if not wallet:
        fail(404,'Wallet not found')
    iid=uuid4()
    run(db,'INSERT INTO central.statement_imports(id,wallet_id,source_reference,payload_hash,evidence_ref) VALUES(:id,:wallet,:source,:hash,:evidence)',id=iid,wallet=wallet_id,source=source,hash=payload_hash,evidence=evidence)
    for item in items:
        if item['currency']!=wallet['currency']:
            fail(422,'Statement currency mismatch')
        prior=row(db,'SELECT * FROM central.statement_items WHERE wallet_id=:wallet AND operator_reference=:ref',wallet=wallet_id,ref=item['operator_reference'])
        if prior:
            for k in ('amount_minor','currency','recipient','occurred_at'):
                left=prior[k].isoformat() if k=='occurred_at' else prior[k]
                right=datetime.fromisoformat(item[k].replace('Z','+00:00')).isoformat() if k=='occurred_at' else item[k]
                if left!=right:
                    fail(409,'Operator receipt reused with changed fields')
            continue
        receipt=row(db,'SELECT p.* FROM central.receipts r JOIN central.payouts p ON p.id=r.payout_id WHERE r.wallet_id=:wallet AND r.provider_reference=:ref',wallet=wallet_id,ref=item['operator_reference'])
        unresolved=row(db,'''SELECT p.* FROM central.attempts a JOIN central.payouts p ON p.id=a.payout_id
            WHERE a.wallet_id=:wallet AND a.provider_reference=:ref AND a.resolved_at IS NULL''',wallet=wallet_id,ref=item['operator_reference'])
        matched=receipt or unresolved
        if matched and (item['amount_minor']!=-matched['amount_minor'] or item['recipient']!=matched['recipient'] or item['currency']!=matched['currency']):
            fail(409,'Operator reference contradicts payment instructions; investigate')
        run(db,'''INSERT INTO central.statement_items(id,import_id,wallet_id,operator_reference,amount_minor,currency,recipient,occurred_at,payout_id)
            VALUES(:id,:import_id,:wallet,:operator_reference,:amount_minor,:currency,:recipient,CAST(:occurred_at AS timestamptz),:payout)''',id=uuid4(),import_id=iid,wallet=wallet_id,payout=matched['id'] if matched else None,**item)
        if unresolved:
            audit(db,actor,'STATEMENT_EVIDENCE_FOR_REVIEW',unresolved['id'],evidence)
        elif not receipt:
            suspense=account(db,f"suspense:{wallet['currency']}",'SUSPENSE',wallet['currency'])
            post(db,f"statement:{wallet_id}:{item['operator_reference']}",'UNEXPECTED_MOVEMENT',
                [(wallet['account_id'],item['amount_minor']),(suspense['id'],-item['amount_minor'])],evidence)
            run(db,'UPDATE central.devices SET quarantined=true WHERE wallet_id=:id',id=wallet_id)
            run(db,'UPDATE central.wallets SET enabled=false WHERE id=:id',id=wallet_id)
            audit(db,actor,'UNEXPECTED_WALLET_MOVEMENT',wallet_id,evidence)
    audit(db,actor,'IMPORT_STATEMENT',iid,evidence)
    return dict(import_id=str(iid))
