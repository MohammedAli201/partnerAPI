"""Real, enrolled EVC phone bridge. No PIN is sent to or stored by this backend."""
import os
from datetime import timedelta
from uuid import uuid4
import backend_core as c
import payment_worker as w
from evc_carrier_response import success_response


def enabled():
    if os.getenv('PHONE_EVC_PAYMENTS_ENABLED')!='true':
        c.fail(503,'Real EVC payment execution is disabled')
    if os.getenv('SMS_PAYOUT_TEST_ENABLED')=='true':
        c.fail(503,'Real EVC and SMS payout modes cannot run together')


def config(db, device):
    settings=c.row(db,'SELECT * FROM phone_evc_settings WHERE device_id=:id',id=device['id'])
    return dict(device_id=str(device['id']),provider_id='evc-plus',payout_account_id=str(device['wallet_id']),
                sim_subscription_id=settings['sim_subscription_id'] if settings else -1,simulation=False)


def configure(db, device, worker, subscription):
    enabled();c.lock(db)
    if worker['simulator'] or not worker.get('enabled') or device['network'].lower()!='evc':
        c.fail(409,'This credential is not provisioned for real EVC')
    old=c.row(db,'SELECT * FROM phone_evc_settings WHERE device_id=:id FOR UPDATE',id=device['id'])
    if old and old['sim_subscription_id']!=subscription and c.row(db,
        'SELECT 1 FROM payout_attempts WHERE device_id=:id AND resolved_at IS NULL',id=device['id']):
        c.fail(409,'Cannot change SIM during an unresolved payment')
    if old and old['sim_subscription_id']!=subscription:
        c.fail(409,'SIM change requires a separately reconciled wallet and enrollment')
    c.run(db,'''INSERT INTO phone_evc_settings(device_id,sim_subscription_id) VALUES(:id,:sub)
        ON CONFLICT(device_id) DO UPDATE SET enabled=true''',id=device['id'],sub=subscription)
    c.audit(db,worker['id'],'EVC_PHONE_CONFIGURED',device['id'])
    return dict(config=config(db,device))


def claim(db, identity):
    from phone_worker import controls, now, millis, payload_hash
    enabled();credential,device,worker=identity
    if controls(db,credential,device)['paused'] or credential['drain']:
        return dict(assignment=None)
    command=w.claim(db,worker,device['id'],evc=True)
    if not command:
        return dict(assignment=None)
    job=dict(payout_id=command['payout_id'],attempt_id=command['attempt_id'],
             assignment_version=command['lease_generation'],recipient=command['recipient'],
             recipient_name=command['recipient_name'],recipient_type='MSISDN',amount_minor=command['amount_minor'],
             currency=command['currency'],flow_version='evc-712-v1',correlation_id=command['payout_id'],scenario='REAL',
             claim_expires_at=millis(now()+timedelta(seconds=100)),
             execution_expires_at=millis(now()+timedelta(seconds=110)),**config(db,device))
    job.pop('simulation')
    job['payload_hash']=payload_hash(job)
    c.run(db,'''INSERT INTO phone_worker_assignments(attempt_id,device_id,payload)
        VALUES(:attempt,:device,CAST(:payload AS jsonb))''',attempt=job['attempt_id'],device=device['id'],payload=c.canonical(job))
    return dict(assignment=job)


def authorize(db, body, identity):
    from phone_worker import bound, controls, now, millis
    enabled();credential,device,worker=identity
    assignment,job=bound(db,body,credential)
    if not assignment['acked'] or assignment['phase']!='PREPARING' or assignment['authorization_id']:
        c.fail(409,'Authorization requires a prepared, acknowledged, never-authorized attempt')
    if controls(db,credential,device)['paused'] or credential['drain'] or job['execution_expires_at']<=millis(now()):
        c.fail(409,'Execution paused or expired')
    attempt,_,_=w.owned(db,worker,body.attempt_id,body.assignment_version)
    if attempt['phase']!='CLAIMED':
        c.fail(409,'Attempt already armed; never resubmit')
    w.arm(db,worker,body.attempt_id,body.assignment_version,attempt['instruction_hash'],evc=True)
    identifier=uuid4();expires=now()+timedelta(seconds=25)
    c.run(db,'''UPDATE phone_worker_assignments SET authorization_id=:auth,authorization_expires_at=:expires
        WHERE attempt_id=:id''',auth=identifier,expires=expires,id=body.attempt_id)
    return dict(authorization_id=str(identifier),attempt_id=str(body.attempt_id),payload_hash=job['payload_hash'],expires_at=millis(expires))


def receive(db,event,credential,worker,assignment,job,hashed):
    from phone_worker import now
    attempt,payout,queue=w.owned(db,worker,event.attempt_id,event.assignment_version,False)
    if event.phase=='SUBMISSION_POSSIBLE' and (not assignment['authorization_expires_at'] or
        event.at>int(assignment['authorization_expires_at'].timestamp()*1000) or event.at>job['execution_expires_at']):
        c.fail(409,'Submission was outside the authorization window')
    terminal=event.phase in {'CONFIRMED_SUCCESS','CONFIRMED_NOT_PAID'}
    evidence=event.evidence
    if terminal:
        local=(event.phase=='CONFIRMED_NOT_PAID' and evidence and evidence.code=='LOCAL_NO_SUBMISSION'
               and not assignment['authorization_id'] and assignment['phase'] in {'RECEIVED','VALIDATED','READY','PREPARING'})
        if not local and (not evidence or evidence.payload_hash!=job['payload_hash'] or
            evidence.amount_minor!=job['amount_minor'] or evidence.currency!=job['currency'] or
            evidence.kind!=('SUCCESS_CONFIRMED' if event.phase=='CONFIRMED_SUCCESS' else 'NOT_PAID_CONFIRMED') or
            evidence.code!=('EvcSuccess' if event.phase=='CONFIRMED_SUCCESS' else 'InsufficientBalance')):
            c.fail(409,'Carrier evidence does not match the assignment')
        if not local and not assignment['authorization_id']:
            c.fail(409,'Carrier result without durable authorization')
    c.run(db,'''INSERT INTO phone_worker_events(event_id,attempt_id,sequence,payload_hash,payload)
        VALUES(:id,:attempt,:seq,:hash,CAST(:payload AS jsonb))''',id=event.event_id,attempt=event.attempt_id,
        seq=event.sequence,hash=hashed,payload=c.canonical(event.model_dump(mode='json',exclude_none=True)))
    live=queue and queue['live'] and queue['generation']==attempt['generation']==event.assignment_version and not attempt['resolved_at'] and attempt['phase']!='UNKNOWN'
    if terminal and not live:
        w.unknown(db,attempt,payout,worker['id'],'LATE_EVC_RESULT_RECONCILIATION')
    elif event.phase=='CONFIRMED_SUCCESS':
        try:
            receipt=success_response(evidence.carrier_response,job,attempt['created_at']-timedelta(minutes=2),now()+timedelta(minutes=2))
        except ValueError:
            c.fail(409,'Carrier response does not confirm this payment')
        if attempt['phase']!='ARMED':
            c.fail(409,'Payment result requires an armed attempt')
        wallet=c.row(db,'SELECT * FROM payout_wallets WHERE id=:id FOR UPDATE',id=attempt['wallet_id'])
        settings=c.row(db,'SELECT * FROM phone_evc_settings WHERE device_id=:id FOR UPDATE',id=credential['device_id'])
        asset=c.row(db,'SELECT * FROM ledger_accounts WHERE id=:id FOR UPDATE',id=wallet['account_id'])
        before=receipt['amount_minor']+receipt['remaining_minor']
        if settings['float_known'] and (asset['balance_minor']!=before or wallet['observed_minor']!=before):
            w.unknown(db,attempt,payout,worker['id'],'CARRIER_BALANCE_RECONCILIATION')
        else:
            ref='android-ussd-event:'+str(event.event_id)
            identity={k:str(v) for k,v in receipt.items() if k!='response_text'}
            identity['recipient_name']=identity['recipient_name'].casefold()
            c.run(db,'''INSERT INTO phone_evc_confirmations(attempt_id,event_id,payout_id,wallet_id,response_hash,
                recipient,recipient_name,amount_minor,remaining_minor,carrier_at,response_text)
                VALUES(:attempt,:event,:payout,:wallet,:hash,:recipient,:recipient_name,:amount_minor,:remaining_minor,:carrier_at,:response_text)''',
                attempt=attempt['id'],event=event.event_id,payout=payout['id'],wallet=wallet['id'],hash=c.digest(identity),**receipt)
            if not settings['float_known']:
                if asset['balance_minor']!=0 or wallet['observed_minor']!=0:
                    c.fail(409,'Unknown wallet must not contain fabricated opening float')
                opening=c.account(db,'evc-carrier-opening:USD','OPENING','USD')
                c.post(db,'evc-opening:'+str(wallet['id']),'CARRIER_OBSERVED_OPENING','USD',
                       [(asset['id'],before),(opening['id'],-before)],ref)
            reservation,payable=c.release_partner(db,payout,True)
            w.wallet_release(db,attempt,'CAPTURED')
            fee=c.minor(reservation['fee'],payout['currency']);fees=c.account(db,'fees:USD','FEES','USD')
            entries=[(payable['id'],receipt['amount_minor']+fee),(asset['id'],-receipt['amount_minor'])]
            if fee:entries.append((fees['id'],-fee))
            c.post(db,'evc-payout:'+str(payout['id']),'PAYOUT','USD',entries,ref,payout['id'])
            c.run(db,"UPDATE payout_attempts SET phase='SUCCESS',resolved_at=now(),evidence_ref=:ref WHERE id=:id",id=attempt['id'],ref=ref)
            c.run(db,'UPDATE payout_wallets SET observed_minor=:n,observed_at=now() WHERE id=:id',id=wallet['id'],n=receipt['remaining_minor'])
            c.run(db,'UPDATE phone_evc_settings SET float_known=true WHERE device_id=:id',id=credential['device_id'])
            c.run(db,"UPDATE payout_queue SET status='DONE' WHERE payout_id=:id",id=payout['id'])
            c.change(db,payout,'SENT',worker['id'],'EVC_CARRIER_RESPONSE_CONFIRMED')
    elif event.phase=='CONFIRMED_NOT_PAID':
        if not local and (evidence.carrier_response or '').strip().rstrip('.')!='Haraaga xisaabtaadu kuguma filna':
            c.fail(409,'Unrecognized nonpayment response')
        c.release_partner(db,payout);w.wallet_release(db,attempt,'RELEASED')
        c.run(db,"UPDATE payout_attempts SET phase='NOT_SENT',resolved_at=now(),evidence_ref=:ref WHERE id=:id",id=attempt['id'],ref='android-ussd-event:'+str(event.event_id))
        c.run(db,"UPDATE payout_queue SET status='DONE' WHERE payout_id=:id",id=payout['id'])
        c.change(db,payout,'FAILED',worker['id'],'EVC_NO_PAYMENT_CONFIRMED')
    elif event.phase in {'UNKNOWN','RECONCILIATION_REQUIRED'}:
        w.unknown(db,attempt,payout,worker['id'],'PHONE_'+event.phase)
    c.run(db,'UPDATE phone_worker_assignments SET phase=:phase,sequence=:seq WHERE attempt_id=:id',id=event.attempt_id,phase=event.phase,seq=event.sequence)
    return dict(ack_event_id=str(event.event_id))
