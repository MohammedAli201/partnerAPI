"""Registered partner destinations and three-stage durable callback delivery."""
import logging
import random
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
from uuid import uuid4
from sqlalchemy import select,or_,and_,text
from models import PayoutWebhookEvent
from webhook_transport import endpoint_url,resolve,send

logger=logging.getLogger(__name__)


def register(db,partner,url,secret,actor):
    from backend_core import lock,row,run,audit,fail
    if len(secret)<32:
        fail(422,'Partner-specific signing secret must have at least 32 characters')
    # DNS lookup/approval takes place BEFORE acquiring database transaction locks.
    normalized=endpoint_url(url)
    addresses=resolve(normalized)
    lock(db)
    if not row(db,'SELECT 1 FROM partners WHERE id=:id',id=partner):
        fail(404,'Partner not found')
    version=row(db,'SELECT COALESCE(max(version),0)+1 AS v FROM webhook_endpoints WHERE partner_id=:id',id=partner)['v']
    run(db,'UPDATE webhook_endpoints SET enabled=false WHERE partner_id=:id AND enabled',id=partner)
    eid=uuid4()
    run(db,'INSERT INTO webhook_endpoints(id,partner_id,url,approved_addresses,signing_secret,version) VALUES(:id,:partner,:url,:addresses,:secret,:version)',id=eid,partner=partner,url=normalized,addresses=addresses,secret=secret,version=version)
    audit(db,actor,'REGISTER_ENDPOINT',eid)
    return dict(endpoint_id=str(eid),version=version)


def enqueue(db,payout,status,event_time,default_url=None):
    from backend_core import row
    import payout_webhooks
    endpoint=row(db,'SELECT * FROM webhook_endpoints WHERE partner_id=:id AND enabled',id=payout.partner_id)
    event=payout_webhooks.build_event(payout,status,event_time,endpoint['url'] if endpoint else None)
    if event:
        event.partner_id=payout.partner_id
        event.endpoint_id=endpoint['id'] if endpoint else None
        event.status_version=payout.status_version
        event.state='READY' if endpoint else 'BLOCKED'
        from backend_core import run
        run(db,'''INSERT INTO payout_webhook_events(event_id,payout_id,callback_url,raw_body,attempts,next_attempt_at,
            created_at,partner_id,endpoint_id,state,generation,status_version)
            VALUES(:event,:payout,:url,:body,0,:next,:created,:partner,:endpoint,:state,0,:version)''',
            event=event.event_id,payout=event.payout_id,url=event.callback_url,body=event.raw_body,
            next=event.next_attempt_at,created=event.created_at,partner=event.partner_id,endpoint=event.endpoint_id,state=event.state,version=event.status_version)
    return event


def deliver_next(session_factory,*unused):
    from payout_webhooks import signed_headers
    now=datetime.now(timezone.utc)
    owner=uuid4()
    with session_factory.begin() as db:
        event=db.execute(select(PayoutWebhookEvent).where(or_(
            and_(PayoutWebhookEvent.state=='READY',PayoutWebhookEvent.next_attempt_at<=now),
            and_(PayoutWebhookEvent.state=='LEASED',PayoutWebhookEvent.lease_until<now)))
            .order_by(PayoutWebhookEvent.created_at).with_for_update(skip_locked=True).limit(1)).scalar_one_or_none()
        if event is None:
            return False
        endpoint=db.execute(text('SELECT * FROM webhook_endpoints WHERE id=:id AND enabled'),dict(id=event.endpoint_id)).mappings().first()
        if not endpoint or endpoint['partner_id']!=event.partner_id or endpoint['url']!=event.callback_url:
            event.state='BLOCKED'
            event.last_error='destination_disabled_or_unregistered'
            return True
        event.state='LEASED'
        event.lease_owner=owner
        event.lease_until=now+timedelta(seconds=30)
        event.generation+=1
        event.attempts+=1
        eid,generation,attempts=event.event_id,event.generation,event.attempts
        # Copy immutable data: sessionmaker defaults expire-on-commit.
        url,addresses,secret,raw=endpoint['url'],list(endpoint['approved_addresses']),endpoint['signing_secret'],bytes(event.raw_body)
    # DNS and HTTP are outside EVERY database transaction/connection.
    code=None
    error=None
    try:
        code=send(url,addresses,raw,signed_headers(secret,raw))
    except Exception as failure:
        # Keep evidence IDs, never log payloads, endpoints or exception strings.
        error=type(failure).__name__[:64]
    with session_factory.begin() as db:
        db.execute(text('''UPDATE payout_webhook_events SET state=:state,accepted_at=:accepted,
            lease_until=NULL,lease_owner=NULL,last_status_code=:code,last_error=:error,next_attempt_at=:next
            WHERE event_id=:id AND generation=:generation AND lease_owner=:owner AND state='LEASED' '''),
            dict(state='DELIVERED' if code==202 else 'READY',accepted=datetime.now(timezone.utc) if code==202 else None,
                code=code,error=error if error else None if code==202 else 'unexpected_acknowledgement',
                next=datetime.now(timezone.utc)+timedelta(seconds=min(3600,5*2**min(attempts-1,10))+random.randint(0,5)),id=eid,generation=generation,owner=owner))
    return True


def run_worker(stop,session_factory,*unused):
    while not stop.is_set():
        try:
            work=deliver_next(session_factory)
        except Exception:
            logger.error('Callback delivery database error; retrying')
            work=False
        if not work:
            stop.wait(2)
