"""Financial operations on existing public partners/payouts/queue records."""
import hashlib
import json
import re
import os
from decimal import Decimal
from datetime import datetime,timezone
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import text


def run(db,sql,**params):
    return db.execute(text(sql),params)

def row(db,sql,**params):
    return run(db,sql,**params).mappings().first()

def fail(code,message):
    raise HTTPException(code,message)

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True)

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def minor(amount,currency):
    if currency not in ('USD','EUR','GBP'):
        fail(422,'Supported funding currencies USD/EUR/GBP have scale 2')
    value=Decimal(str(amount))
    if not value.is_finite() or value!=value.quantize(Decimal('.01')) or abs(value)>Decimal('1000000000000'):
        fail(422,'Finite exact scale-2 money required; rounding is not performed')
    return int(value*100)

def lock(db):
    # One short financial lock initially; no network work inside this transaction.
    run(db,'SELECT pg_advisory_xact_lock(90261009)')

def audit(db,actor,action,target,evidence='none'):
    run(db,'INSERT INTO payment_audit VALUES(:id,:actor,:action,:target,:evidence,now())',id=uuid4(),actor=str(actor),action=action,target=str(target),evidence=evidence)

def account(db,key,kind,currency,partner=None):
    run(db,'''INSERT INTO ledger_accounts(id,business_key,partner_id,currency,kind)
        VALUES(:id,:key,:partner,:currency,:kind) ON CONFLICT(business_key) DO NOTHING''',id=uuid4(),key=key,partner=partner,currency=currency,kind=kind)
    a=row(db,'SELECT * FROM ledger_accounts WHERE business_key=:key FOR UPDATE',key=key)
    if a['kind']!=kind or a['currency']!=currency or a['partner_id']!=partner:
        fail(409,'Account identity conflict')
    return a

def funding_account(db,partner,currency):
    return account(db,f'partner:{partner}:{currency}','PARTNER',currency,partner)

def post(db,key,event,currency,entries,evidence,payout=None,reversal=None):
    if not evidence or len(entries)<2 or sum(n for _,n in entries)!=0 or any(not isinstance(n,int) or n==0 for _,n in entries):
        fail(422,'Posting must have balanced nonzero integer entries and evidence')
    old=row(db,'SELECT * FROM ledger_journals WHERE business_event_key=:key',key=key)
    if old:
        stored=run(db,'SELECT account_id,amount_minor FROM ledger_entries WHERE journal_id=:id ORDER BY account_id,amount_minor',id=old['id']).all()
        expected=sorted(entries,key=lambda pair:(str(pair[0]),pair[1]))
        if [(str(a),n) for a,n in stored]!=[(str(a),n) for a,n in expected] or old['evidence_ref']!=evidence or old['event_type']!=event or old['currency']!=currency or old['payout_id']!=payout:
            fail(409,'Financial event key changed')
        return old['id']
    for aid in sorted({a for a,_ in entries},key=str):
        a=row(db,'SELECT * FROM ledger_accounts WHERE id=:id FOR UPDATE',id=aid)
        if not a or a['currency']!=currency:
            fail(422,'Account currency mismatch')
    jid=uuid4()
    run(db,'''INSERT INTO ledger_journals(id,business_event_key,currency,payout_id,event_type,evidence_ref,reversal_of)
        VALUES(:id,:key,:currency,:payout,:event,:evidence,:reversal)''',id=jid,key=key,currency=currency,payout=payout,event=event,evidence=evidence,reversal=reversal)
    for aid,n in entries:
        run(db,'INSERT INTO ledger_entries VALUES(:id,:journal,:account,:currency,:amount)',id=uuid4(),journal=jid,account=aid,currency=currency,amount=n)
    return jid

def opening_propose(db,partner,user,available,reserved,evidence):
    lock(db)
    p=row(db,'SELECT * FROM partners WHERE id=:id FOR UPDATE',id=partner)
    if not p or p['ledger_enabled']:
        fail(409,'Partner missing or already reconciled')
    av,rs=minor(available,p['funding_currency']),minor(reserved,p['funding_currency'])
    if (av,rs)!=(minor(p['balance_available'],p['funding_currency']),minor(p['balance_reserved'],p['funding_currency'])):
        fail(409,'Opening evidence does not reconcile legacy balances; resolve differences first')
    iid=uuid4()
    run(db,'''INSERT INTO opening_reviews(id,partner_id,currency,available_minor,reserved_minor,evidence_ref,proposer)
        VALUES(:id,:partner,:currency,:available,:reserved,:evidence,:user)''',id=iid,partner=partner,currency=p['funding_currency'],available=av,reserved=rs,evidence=evidence,user=user)
    audit(db,user,'PROPOSE_OPENING',partner,evidence)
    return dict(review_id=str(iid))

def opening_approve(db,review,user):
    lock(db)
    r=row(db,'SELECT * FROM opening_reviews WHERE id=:id FOR UPDATE',id=review)
    if not r:
        fail(404,'Opening review missing')
    if r['approved_at']:
        return dict(enabled=True)
    if r['proposer']==user:
        fail(409,'Independent opening reviewer required')
    p=row(db,'SELECT * FROM partners WHERE id=:id FOR UPDATE',id=r['partner_id'])
    if p['ledger_enabled'] or (minor(p['balance_available'],r['currency']),minor(p['balance_reserved'],r['currency']))!=(r['available_minor'],r['reserved_minor']):
        fail(409,'Legacy balances changed since review')
    active=row(db,"SELECT COALESCE(sum(total),0) AS total FROM payout_reservations WHERE partner_id=:id AND status='ACTIVE'",id=p['id'])['total']
    incompatible=row(db,"SELECT 1 FROM payout_reservations r JOIN payouts p ON p.id=r.payout_id WHERE r.partner_id=:id AND r.status='ACTIVE' AND p.currency<>:currency",id=p['id'],currency=r['currency'])
    if incompatible or minor(active,r['currency'])!=r['reserved_minor']:
        fail(409,'Legacy reservations/currency do not reconcile')
    if row(db,"SELECT 1 FROM payouts WHERE partner_id=:id GROUP BY lower(right(partner_tx_id,36)) HAVING count(*)>1",id=p['id']):
        fail(409,'Legacy reference aliases require manual reconciliation')
    a=funding_account(db,p['id'],r['currency'])
    contra=account(db,f"opening:{r['currency']}",'OPENING',r['currency'])
    total=r['available_minor']+r['reserved_minor']
    if total:
        post(db,f"opening:{p['id']}:{r['currency']}",'OPENING',r['currency'],[(contra['id'],total),(a['id'],-total)],r['evidence_ref'])
    run(db,'UPDATE ledger_accounts SET reserved_minor=:reserved WHERE id=:id',reserved=r['reserved_minor'],id=a['id'])
    run(db,'UPDATE partners SET ledger_enabled=true WHERE id=:id',id=p['id'])
    run(db,'UPDATE opening_reviews SET approver=:user,approved_at=now() WHERE id=:id',user=user,id=review)
    audit(db,user,'APPROVE_OPENING',p['id'],r['evidence_ref'])
    return dict(enabled=True)

def immutable(payload,reference):
    data=dict(payload.request_payload)
    if payload.payout_channel:
        data['payout_channel']=payload.payout_channel
    from payout_webhooks import payout_channel
    return dict(version=1,reference=reference.rsplit('_',1)[-1].lower(),amount_minor=minor(payload.amount,payload.currency.upper()),
        currency=payload.currency.strip().upper(),recipient=payload.recipient.strip(),provider=payload.provider.strip().lower(),
        network=payout_channel(data).strip().lower(),corridor=str(data.get('corridor','SO')).strip().upper())

def stored_instructions(p):
    from payout_webhooks import payout_channel
    metadata=json.loads(p['request_payload'] or '{}')
    return dict(version=1,reference=p['partner_tx_id'].rsplit('_',1)[-1].lower(),amount_minor=minor(p['amount'],p['currency'].upper()),currency=p['currency'].upper(),
        recipient=p['recipient'].strip(),provider=p['provider'].strip().lower(),network=payout_channel(metadata).strip().lower(),corridor=str(metadata.get('corridor','SO')).strip().upper())

def admission(db,partner,payload,reference,key,fee):
    try:
        instructions=immutable(payload,reference)
    except ValueError as error:
        fail(422,str(error))
    hashed=digest(instructions)
    if key is not None and (not isinstance(key,str) or not 1<=len(key)<=128 or key!=key.strip()):
        fail(422,'Invalid Idempotency-Key')
    if not re.fullmatch(r'\+[1-9][0-9]{7,14}',instructions['recipient']):
        fail(422,'E.164 recipient required')
    lock(db)
    p=row(db,'SELECT * FROM partners WHERE id=:id FOR UPDATE',id=partner)
    if not p or not p['is_active']:
        fail(401,'Partner unavailable')
    previous=row(db,"SELECT * FROM payout_idempotency WHERE partner_id=:partner AND operation='CREATE' AND idempotency_key=:key",partner=partner,key=key) if key else None
    if previous:
        if previous['payload_hash']!=hashed:
            fail(409,'Idempotency key instructions changed')
        return previous['response']
    external=instructions['reference']
    existing=row(db,'SELECT p.* FROM payout_reference_aliases a JOIN payouts p ON p.id=a.payout_id WHERE a.partner_id=:partner AND a.external_reference=:reference',partner=partner,reference=external)
    if existing:
        if (existing['canonical_hash'] or digest(stored_instructions(existing)))!=hashed:
            fail(409,'External reference instructions changed')
        response=dict(id=str(existing['id']),partner_tx_id=existing['partner_tx_id'],status=existing['status'],created_at=existing['created_at'].isoformat(),duplicate=True,message='Transaction already exists')
    else:
        if p['paused'] or not p['ledger_enabled']:
            fail(409,'Partner funding requires approved reconciliation or is paused')
        if instructions['currency']!=p['funding_currency']:
            fail(422,'Payout currency must match partner funding; no implicit FX')
        metadata=dict(payload.request_payload)
        metadata['payout_channel']=instructions['network']
        endpoint=row(db,'SELECT * FROM webhook_endpoints WHERE partner_id=:id AND enabled',id=partner)
        requested=metadata.pop('callback_url',None)
        if requested:
            from webhook_transport import endpoint_url
            try:
                normalized=endpoint_url(requested)
            except ValueError:
                fail(422,'Register an approved HTTPS webhook endpoint first')
            if not endpoint or normalized!=endpoint['url']:
                fail(409,'Per-payout callback must match registered partner endpoint')
        amount=Decimal(instructions['amount_minor'])/100
        fee_minor=minor(fee,p['funding_currency'])
        if fee_minor<0:
            fail(422,'The configured payout fee must be nonnegative')
        total=instructions['amount_minor']+fee_minor
        a=funding_account(db,partner,p['funding_currency'])
        changed=row(db,'UPDATE ledger_accounts SET reserved_minor=reserved_minor+:total WHERE id=:id AND balance_minor-reserved_minor>=:total RETURNING id',id=a['id'],total=total)
        if not changed:
            fail(402,'Insufficient partner funding')
        pid=uuid4()
        # Partner/account lock makes the business unit serial; uniqueness is still
        # the authority, and instructions are NEVER overwritten by conflict handling.
        inserted=row(db,'''INSERT INTO payouts(id,partner_id,partner_tx_id,amount,currency,recipient,provider,status,request_payload,canonical_hash)
            VALUES(:id,:partner,:reference,:amount,:currency,:recipient,:provider,'RECEIVED',:payload,:hash)
            ON CONFLICT(partner_id,partner_tx_id) DO NOTHING RETURNING *''',id=pid,partner=partner,reference=reference,amount=amount,currency=instructions['currency'],recipient=instructions['recipient'],provider=payload.provider.strip(),payload=canonical(metadata),hash=hashed)
        if not inserted:
            # Impossible between cooperating admissions under this lock. Never leave
            # a second reserve if an unrelated writer inserted concurrently.
            fail(409,'Concurrent reference insertion; retry to resolve canonical instructions')
        run(db,'INSERT INTO payout_reference_aliases VALUES(:partner,:reference,:payout)',partner=partner,reference=external,payout=pid)
        run(db,"INSERT INTO payout_reservations(payout_id,partner_id,amount,fee,total,status,created_at) VALUES(:id,:partner,:amount,:fee,:total,'ACTIVE',now())",id=pid,partner=partner,amount=amount,fee=Decimal(fee_minor)/100,total=Decimal(total)/100)
        from config import get_settings
        run(db,"""INSERT INTO payout_fee_snapshots VALUES(:payout,:partner,:currency,:fee,:policy,
          CAST(:components AS jsonb),:activity,'ADMISSION_SNAPSHOT',:accepted)""",
          payout=pid,partner=partner,currency=instructions['currency'],fee=fee_minor,
          policy=os.getenv('FEE_POLICY_VERSION') or get_settings().fee_policy_version,
          components=canonical(dict(type='fixed',amount_minor=fee_minor)),
          activity='live' if os.getenv('ENVIRONMENT')=='production' else 'simulation',accepted=inserted['created_at'])
        run(db,"INSERT INTO payout_queue(payout_id,status,created_at) VALUES(:id,'PENDING',now())",id=pid)
        run(db,"INSERT INTO payout_history VALUES(:id,:payout,1,NULL,'RECEIVED',:actor,'ADMITTED',now())",id=uuid4(),payout=pid,actor=f'partner:{partner}')
        response=dict(id=str(pid),partner_tx_id=reference,status='RECEIVED',created_at=inserted['created_at'].isoformat(),duplicate=False,
            fee=str(Decimal(fee_minor)/100),charged_total=str(Decimal(total)/100),balances=dict(available=str(Decimal(a['balance_minor']-a['reserved_minor']-total)/100),reserved=str(Decimal(a['reserved_minor']+total)/100),total=str(Decimal(a['balance_minor'])/100)))
    if key:
        run(db,"INSERT INTO payout_idempotency VALUES(:partner,'CREATE',:key,:hash,:payout,CAST(:response AS jsonb),now())",partner=partner,key=key,hash=hashed,payout=response['id'],response=canonical(response))
    return response

def change(db,p,status,actor,reason):
    if p['status']==status:
        return p
    if p['status'] in ('SENT','FAILED','REJECTED','CANCELLED'):
        fail(409,'Final payout cannot regress')
    updated=row(db,'UPDATE payouts SET status=:status,status_version=status_version+1,hold_reason=:reason,updated_at=now() WHERE id=:id RETURNING *',status=status,reason=reason if status=='UNKNOWN' else None,id=p['id'])
    run(db,'INSERT INTO payout_history VALUES(:id,:payout,:version,:old,:new,:actor,:reason,now())',id=uuid4(),payout=p['id'],version=updated['status_version'],old=p['status'],new=status,actor=str(actor),reason=reason)
    from payout_webhooks import enqueue_event
    from types import SimpleNamespace
    enqueue_event(db,SimpleNamespace(**updated),status,datetime.now(timezone.utc),None)
    return updated

def release_partner(db,p,capture=False):
    r=row(db,"SELECT * FROM payout_reservations WHERE payout_id=:id AND status='ACTIVE' FOR UPDATE",id=p['id'])
    if not r:
        fail(409,'Active partner reservation missing')
    a=funding_account(db,p['partner_id'],p['currency'])
    run(db,'UPDATE ledger_accounts SET reserved_minor=reserved_minor-:total WHERE id=:id',id=a['id'],total=minor(r['total'],p['currency']))
    run(db,'UPDATE payout_reservations SET status=:status WHERE payout_id=:id',status='CAPTURED' if capture else 'RELEASED',id=p['id'])
    return r,a

def deposit(db,partner,amount,reference,evidence,actor):
    lock(db)
    p=row(db,'SELECT * FROM partners WHERE id=:id FOR UPDATE',id=partner)
    if not p or not p['ledger_enabled']:
        fail(409,'Reconcile opening funding first')
    if not reference or not evidence:
        fail(422,'Funding reference and evidence required')
    n=minor(amount,p['funding_currency'])
    if n<=0:
        fail(422,'Positive funding required')
    payable=funding_account(db,partner,p['funding_currency'])
    bank=account(db,f"bank:{p['funding_currency']}",'BANK',p['funding_currency'])
    before=p['balance_available']
    jid=post(db,f'prefund:{partner}:{reference}','PREFUND',p['funding_currency'],[(bank['id'],n),(payable['id'],-n)],evidence)
    run(db,'''INSERT INTO balance_transactions(partner_id,type,amount,previous_balance,new_balance,reference,admin_user,ledger_journal_id)
        VALUES(:partner,'deposit',:amount,:before,:after,:reference,:actor,:journal) ON CONFLICT(ledger_journal_id) DO NOTHING''',
        partner=partner,amount=Decimal(n)/100,before=before,after=before+Decimal(n)/100,reference=reference,actor=str(actor),journal=jid)
    audit(db,actor,'PREFUND',partner,evidence)
    p=row(db,'SELECT * FROM partners WHERE id=:id',id=partner)
    return dict(success=True,ok=True,journal_id=str(jid),partner_id=partner,balances=dict(available=str(p['balance_available']),reserved=str(p['balance_reserved']),total=str(p['balance_available']+p['balance_reserved'])))
