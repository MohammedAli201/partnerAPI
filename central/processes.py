"""Separate callback/reaper/recovery processes: python -m central.processes ..."""
import argparse
import hashlib
import hmac
import random
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from central.app import transaction
from central import service as s


def deliver_one(engine, sender=None):
    with engine.begin() as db:
        delivery=s.row(db,"""SELECT * FROM central.deliveries WHERE
            (state='READY' AND next_attempt_at<=now()) OR (state='LEASED' AND lease_until<now())
            ORDER BY next_attempt_at FOR UPDATE SKIP LOCKED LIMIT 1""")
        if not delivery:
            return False
        delivery=s.row(db,"""UPDATE central.deliveries SET state='LEASED',lease_until=now()+interval '60 seconds',
            generation=generation+1,attempts=attempts+1 WHERE event_id=:id RETURNING *""",id=delivery['event_id'])
        event=s.row(db,'SELECT * FROM central.outbox WHERE id=:id',id=delivery['event_id'])
    # HTTP starts after commit. Delivery ownership generation fences late acknowledgements.
    raw=s.canonical(event['payload']).encode()
    stamp=str(int(datetime.now(timezone.utc).timestamp()))
    nonce=str(uuid4())
    signature=hmac.new(delivery['signing_secret'].encode(),f'{stamp}.{nonce}.'.encode()+raw,hashlib.sha256).hexdigest()
    headers={'Content-Type':'application/json','X-Payout-Timestamp':stamp,'X-Payout-Nonce':nonce,'X-Payout-Signature':signature}
    code=None
    error=None
    try:
        if sender:
            code=sender(delivery['destination_url'],raw,headers)
        else:
            with httpx.Client(timeout=15,follow_redirects=False,trust_env=False) as client:
                code=client.post(delivery['destination_url'],content=raw,headers=headers).status_code
    except (httpx.HTTPError,OSError):
        error='transport_error'  # No URLs, bodies, tokens, or recipient data in logs.
    with engine.begin() as db:
        delay=min(3600,5*2**min(delivery['attempts']-1,10))+random.randint(0,5)
        s.run(db,"""UPDATE central.deliveries SET state=:state,next_attempt_at=now()+make_interval(secs=>:delay),
            accepted_at=CASE WHEN :accepted THEN now() ELSE NULL END,last_code=:code,last_error=:error,
            lease_until=NULL WHERE event_id=:id AND generation=:generation AND state='LEASED'""",
            state='DELIVERED' if code==202 else 'READY',delay=delay,accepted=code==202,
            code=code,error=error,id=delivery['event_id'],generation=delivery['generation'])
    return True


def recovery_pause(db, reason):
    s.money_lock(db)
    s.run(db,"""INSERT INTO central.controls VALUES('global','all',true,:reason)
        ON CONFLICT(scope,identity) DO UPDATE SET paused=true,reason=EXCLUDED.reason""",reason=reason)
    attempts=s.run(db,'SELECT * FROM central.attempts WHERE resolved_at IS NULL FOR UPDATE').mappings().all()
    for a in attempts:
        p=s.get_payout(db,a['payout_id'])
        # A restored database can show CLAIMED even though the external phone paid.
        s.unknown(db,a,p,'recovery','RESTORE_REQUIRES_EXTERNAL_RECONCILIATION')
    s.audit(db,'recovery','RECOVERY_PAUSE','global',reason)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['callbacks','reaper','recovery-pause'])
    parser.add_argument('--reason',default='Restart/restore: compare worker journals and authoritative statements')
    args=parser.parse_args()
    if args.mode=='recovery-pause':
        with transaction() as db:
            recovery_pause(db,args.reason)
        return
    from central.app import engine
    while True:
        if args.mode=='callbacks':
            did_work=deliver_one(engine())
        else:
            with transaction() as db:
                did_work=s.reap(db)
        if not did_work:
            time.sleep(3)


if __name__=='__main__':
    main()
