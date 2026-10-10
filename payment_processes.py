"""Always-on work independent of HTTP traffic: callbacks, reaper, recovery."""
import argparse
import time
import logging
from threading import Event
from datetime import datetime,timezone
from uuid import uuid4
import backend_core as c
import payment_worker as w


def recovery(db,reason):
    c.lock(db)
    c.run(db,"INSERT INTO payment_controls VALUES('global','all',true,:reason) ON CONFLICT(scope,identity) DO UPDATE SET paused=true,reason=EXCLUDED.reason",reason=reason)
    for a in c.run(db,'SELECT * FROM payout_attempts WHERE resolved_at IS NULL FOR UPDATE').mappings().all():
        p=c.row(db,'SELECT * FROM payouts WHERE id=:id FOR UPDATE',id=a['payout_id'])
        w.unknown(db,a,p,'recovery','RESTORE_MAY_PREDATE_ARMING')
    c.audit(db,'recovery','PAUSE_EXECUTION','global',reason)


def main():
    from database import SessionLocal
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['callbacks','reaper','recovery'])
    parser.add_argument('--reason',default='Restart/restore: reconcile operator records and worker journals')
    args=parser.parse_args()
    if args.mode=='callbacks':
        from registered_webhooks import run_worker
        run_worker(Event(),SessionLocal)
    elif args.mode=='recovery':
        with SessionLocal.begin() as db:
            recovery(db,args.reason)
    else:
        while True:
            try:
                with SessionLocal.begin() as db:
                    w.reap(db)
                    c.run(db,'DELETE FROM rate_buckets WHERE expires_at<now()')
            except Exception as error:
                logging.getLogger(__name__).error('Reaper unavailable; retrying (%s)',type(error).__name__)
            time.sleep(3)


if __name__=='__main__':
    main()
