"""Internal fee reports from immutable ledger entries, in exact minor units."""
import csv
import io
import os
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field
import backend_core as c


def money(n):
    return format(Decimal(n or 0)/100,'.2f')


def period(preset='month', start=None, end=None, now=None):
    from config import get_settings
    try:
        tz=ZoneInfo(os.getenv('REPORTING_TIMEZONE') or get_settings().reporting_timezone)
    except ZoneInfoNotFoundError:
        c.fail(503,'Reporting timezone is not configured correctly')
    today=(now or datetime.now(timezone.utc)).astimezone(tz).date()
    if preset=='today':
        first,last=today,today
    elif preset=='7days':
        first,last=today-timedelta(days=6),today
    elif preset=='month':
        first,last=today.replace(day=1),today
    elif preset=='custom' and start and end:
        first,last=start,end
    else:
        c.fail(422,'Choose today, 7days, month, or custom dates')
    if last<first or (last-first).days>3660:
        c.fail(422,'Invalid reporting period (maximum 10 years)')
    return dict(start=datetime.combine(first,time.min,tz).astimezone(timezone.utc),
                end=datetime.combine(last+timedelta(days=1),time.min,tz).astimezone(timezone.utc),
                timezone=str(tz),start_date=first.isoformat(),end_date=last.isoformat())


def filters(preset: str='month',start: date|None=None,end: date|None=None,
            partner_id: int|None=Query(None,gt=0),currency: str='USD',activity: str='live'):
    if currency not in ('USD','EUR','GBP') or activity not in ('live','simulation','unclassified'):
        c.fail(422,'Choose one supported currency and one activity type')
    return {**period(preset,start,end),'partner':partner_id,'currency':currency,'activity':activity}


SCOPE='s.currency=:currency AND s.activity=:activity AND (CAST(:partner AS integer) IS NULL OR s.partner_id=:partner)'
EVENT_SCOPE='currency=:currency AND activity=:activity AND (CAST(:partner AS integer) IS NULL OR partner_id=:partner)'
DETAIL_SCOPE=f'''{SCOPE} AND (
 s.accepted_at>=:start AND s.accepted_at<:end OR r.status='ACTIVE' OR EXISTS(
 SELECT 1 FROM fee_financial_events ev WHERE ev.payout_id=s.payout_id AND ev.posted_at>=:start AND ev.posted_at<:end))'''


def summary(db,f):
    row=c.row(db,f'''SELECT COALESCE(sum(amount_minor) FILTER(WHERE event_type='PAYOUT'),0) gross,
      COALESCE(sum(amount_minor) FILTER(WHERE event_type='FEE_REVERSAL'),0) reversals
      FROM fee_financial_events WHERE {EVENT_SCOPE} AND posted_at>=:start AND posted_at<:end''',**f)
    pending=c.run(db,f'''SELECT COALESCE(sum(s.fee_minor),0) FROM payout_fee_snapshots s
      JOIN payout_reservations r ON r.payout_id=s.payout_id WHERE {SCOPE} AND r.status='ACTIVE' ''',**f).scalar()
    gaps=c.run(db,f'''SELECT count(*) FROM payouts p LEFT JOIN payout_fee_snapshots s ON s.payout_id=p.id
      WHERE p.currency=:currency AND (CAST(:partner AS integer) IS NULL OR p.partner_id=:partner)
      AND (s.payout_id IS NULL OR s.evidence_state='RECONCILIATION_REQUIRED')''',**f).scalar()
    return dict(gross=money(row['gross']),reversals=money(row['reversals']),net=money(row['gross']-row['reversals']),
                pending=money(pending),currency=f['currency'],activity=f['activity'],timezone=f['timezone'],
                start_date=f['start_date'],end_date=f['end_date'],snapshot_at=datetime.now(timezone.utc).isoformat(),
                reconciliation_required=gaps,costs='unavailable',collection='Fees deducted from prefunded partner liabilities on success; bank settlement is not tracked here.')


def partners(db,f,limit=100,offset=0):
    return c.run(db,f'''WITH events AS (
       SELECT partner_id,sum(amount_minor) FILTER(WHERE event_type='PAYOUT') gross,
         sum(amount_minor) FILTER(WHERE event_type='FEE_REVERSAL') reversals
       FROM fee_financial_events WHERE {EVENT_SCOPE} AND posted_at>=:start AND posted_at<:end GROUP BY partner_id
    ), pending AS (
       SELECT s.partner_id,sum(s.fee_minor) pending FROM payout_fee_snapshots s
       JOIN payout_reservations r ON r.payout_id=s.payout_id WHERE {SCOPE} AND r.status='ACTIVE' GROUP BY s.partner_id
    ), counts AS (
       SELECT s.partner_id,count(*) payout_count FROM payout_fee_snapshots s JOIN payout_reservations r ON r.payout_id=s.payout_id
       WHERE {DETAIL_SCOPE} GROUP BY s.partner_id
    ) SELECT p.id,p.name,COALESCE(e.gross,0) gross,COALESCE(e.reversals,0) reversals,
      COALESCE(e.gross,0)-COALESCE(e.reversals,0) net,COALESCE(h.pending,0) pending,COALESCE(n.payout_count,0) payout_count
      FROM partners p LEFT JOIN events e ON e.partner_id=p.id LEFT JOIN pending h ON h.partner_id=p.id
      LEFT JOIN counts n ON n.partner_id=p.id
      WHERE (CAST(:partner AS integer) IS NULL OR p.id=:partner) AND (n.partner_id IS NOT NULL OR e.partner_id IS NOT NULL)
      ORDER BY p.id LIMIT :limit OFFSET :offset''',**f,limit=limit,offset=offset).mappings().all()


DETAIL_SELECT='''SELECT p.id payout_id,COALESCE(ref.external_reference,p.partner_tx_id) external_reference,
 p.partner_tx_id stored_reference,p.amount principal,p.currency,p.status payout_state,
 p.partner_id,partner.name partner,s.fee_minor original_fee_minor,s.policy_version,s.activity,s.evidence_state,
 CASE WHEN x.gross>0 THEN CASE WHEN x.reversed=x.gross THEN 'REVERSED' WHEN x.reversed>0 THEN 'PARTIALLY_REVERSED' ELSE 'EARNED' END
 WHEN r.status='ACTIVE' THEN 'PENDING' WHEN p.status='SENT' AND s.fee_minor=0 THEN 'ZERO_FEE'
 WHEN p.status='SENT' THEN 'RECONCILIATION_REQUIRED' ELSE 'RELEASED' END fee_state,
 x.recognized_at,x.reversed_at,COALESCE(x.gross,0) lifetime_gross_minor,COALESCE(x.reversed,0) reversed_minor,
 COALESCE(x.period_gross,0) period_gross_minor,COALESCE(x.period_reversed,0) period_reversed_minor,
 CASE WHEN r.status='ACTIVE' THEN s.fee_minor ELSE 0 END pending_fee_minor,
 COALESCE(x.events,'[]'::jsonb) financial_events,s.accepted_at
 FROM payout_fee_snapshots s JOIN payouts p ON p.id=s.payout_id JOIN partners partner ON partner.id=s.partner_id
 JOIN payout_reservations r ON r.payout_id=s.payout_id
 LEFT JOIN payout_reference_aliases ref ON ref.partner_id=p.partner_id AND ref.external_reference=lower(right(p.partner_tx_id,36))
 LEFT JOIN LATERAL (SELECT sum(ev.amount_minor) FILTER(WHERE ev.event_type='PAYOUT') gross,
 sum(ev.amount_minor) FILTER(WHERE ev.event_type='FEE_REVERSAL') reversed,
 sum(ev.amount_minor) FILTER(WHERE ev.event_type='PAYOUT' AND ev.posted_at>=:start AND ev.posted_at<:end) period_gross,
 sum(ev.amount_minor) FILTER(WHERE ev.event_type='FEE_REVERSAL' AND ev.posted_at>=:start AND ev.posted_at<:end) period_reversed,
 min(ev.posted_at) FILTER(WHERE ev.event_type='PAYOUT') recognized_at,
 max(ev.posted_at) FILTER(WHERE ev.event_type='FEE_REVERSAL') reversed_at,
 jsonb_agg(jsonb_build_object('journal_id',ev.journal_id,'event_reference',ev.business_event_key,
 'event_type',ev.event_type,'amount_minor',ev.amount_minor,'posted_at',ev.posted_at,'reversal_of',ev.reversal_of,
 'reason',review.reason,'evidence_ref',ev.evidence_ref) ORDER BY ev.posted_at,ev.journal_id) events
 FROM fee_financial_events ev LEFT JOIN fee_reversal_reviews review ON review.journal_id=ev.journal_id
 WHERE ev.payout_id=s.payout_id) x ON true'''


def details(db,f,limit=50,offset=0,sort='accepted_desc',state=None):
    orders={'accepted_desc':'accepted_at DESC,payout_id','accepted_asc':'accepted_at,payout_id',
            'fee_desc':'original_fee_minor DESC,payout_id','recognized_desc':'recognized_at DESC NULLS LAST,payout_id'}
    if sort not in orders or state not in (None,'PENDING','EARNED','REVERSED','PARTIALLY_REVERSED','RELEASED','RECONCILIATION_REQUIRED','ZERO_FEE'):
        c.fail(422,'Invalid detail sorting or state')
    sql=f'''WITH detail AS ({DETAIL_SELECT} WHERE {DETAIL_SCOPE}) SELECT * FROM detail
      WHERE (CAST(:state AS text) IS NULL OR fee_state=:state) ORDER BY {orders[sort]} LIMIT :limit OFFSET :offset'''
    if state is None and sort!='recognized_desc':
        candidate_order={'accepted_desc':'s.accepted_at DESC,s.payout_id',
          'accepted_asc':'s.accepted_at,s.payout_id','fee_desc':'s.fee_minor DESC,s.payout_id'}[sort]
        sql=f'''WITH page AS MATERIALIZED (SELECT s.payout_id FROM payout_fee_snapshots s
          JOIN payout_reservations r ON r.payout_id=s.payout_id WHERE {DETAIL_SCOPE}
          ORDER BY {candidate_order} LIMIT :limit OFFSET :offset),
          detail AS ({DETAIL_SELECT} WHERE s.payout_id IN (SELECT payout_id FROM page))
          SELECT * FROM detail ORDER BY {orders[sort]}'''
    rows=c.run(db,sql,**f,state=state,limit=limit,offset=offset).mappings().all()
    result=[]
    for record in rows:
        r=dict(record)
        r.update(original_fee=money(r['original_fee_minor']),gross_earned=money(r['lifetime_gross_minor']),
                 reversed=money(r['reversed_minor']),net=money(r['lifetime_gross_minor']-r['reversed_minor']),
                 period_gross=money(r['period_gross_minor']),period_reversals=money(r['period_reversed_minor']),
                 period_net=money(r['period_gross_minor']-r['period_reversed_minor']),pending_fee=money(r['pending_fee_minor']))
        result.append(r)
    if state is None:
        total=c.run(db,f'''SELECT count(*) FROM payout_fee_snapshots s JOIN payout_reservations r ON r.payout_id=s.payout_id
          WHERE {DETAIL_SCOPE}''',**f).scalar()
    else:
        total=c.run(db,f'''WITH detail AS ({DETAIL_SELECT} WHERE {DETAIL_SCOPE})
           SELECT count(*) FROM detail WHERE fee_state=:state''',**f,state=state).scalar()
    return dict(items=result,total=total,limit=limit,offset=offset)


class Reversal(BaseModel):
    model_config=ConfigDict(extra='forbid')
    payout_id: UUID
    amount_minor: int=Field(strict=True,gt=0,le=1000000000000)
    business_reference: str=Field(min_length=1,max_length=128)
    reason: str=Field(min_length=8,max_length=512)
    evidence_ref: str=Field(min_length=8,max_length=512)


def propose(db,body,user):
    c.lock(db)
    snapshot=c.row(db,'SELECT * FROM payout_fee_snapshots WHERE payout_id=:id',id=body.payout_id)
    if not snapshot:
        c.fail(404,'Fee snapshot missing')
    old=c.row(db,'SELECT * FROM fee_reversal_reviews WHERE business_reference=:ref',ref=body.business_reference)
    if old:
        if any(old[k]!=getattr(body,k) for k in ('payout_id','amount_minor','reason','evidence_ref')):
            c.fail(409,'Reversal reference reused with different instructions')
        return dict(review_id=str(old['id']))
    earned=c.row(db,"SELECT sum(amount_minor) FILTER(WHERE event_type='PAYOUT') gross,COALESCE(sum(amount_minor) FILTER(WHERE event_type='FEE_REVERSAL'),0) reversed FROM fee_financial_events WHERE payout_id=:id",id=body.payout_id)
    if not earned['gross'] or body.amount_minor>earned['gross']-earned['reversed']:
        c.fail(409,'Reversal exceeds recognized unreversed fee')
    rid=uuid4()
    c.run(db,'''INSERT INTO fee_reversal_reviews(id,payout_id,business_reference,amount_minor,reason,evidence_ref,proposer)
       VALUES(:id,:payout,:ref,:amount,:reason,:evidence,:user)''',id=rid,payout=body.payout_id,ref=body.business_reference,
       amount=body.amount_minor,reason=body.reason,evidence=body.evidence_ref,user=user)
    c.audit(db,user,'PROPOSE_FEE_REVERSAL',rid,body.evidence_ref)
    return dict(review_id=str(rid))


def approve(db,review,user):
    c.lock(db)
    r=c.row(db,'SELECT * FROM fee_reversal_reviews WHERE id=:id FOR UPDATE',id=review)
    if not r:
        c.fail(404,'Reversal review missing')
    if r['proposer']==user:
        c.fail(403,'A different active administrator must approve')
    if r['journal_id']:
        return dict(journal_id=str(r['journal_id']))
    p=c.row(db,'SELECT * FROM payout_fee_snapshots WHERE payout_id=:id',id=r['payout_id'])
    original=c.row(db,"SELECT * FROM fee_financial_events WHERE payout_id=:id AND event_type='PAYOUT'",id=p['payout_id'])
    reversed=c.run(db,"SELECT COALESCE(sum(amount_minor),0) FROM fee_financial_events WHERE payout_id=:id AND event_type='FEE_REVERSAL'",id=p['payout_id']).scalar()
    if not original or r['amount_minor']>original['amount_minor']-reversed:
        c.fail(409,'Reversal exceeds remaining recognized fee')
    fees=c.account(db,f"fees:{p['currency']}",'FEES',p['currency'])
    payable=c.funding_account(db,p['partner_id'],p['currency'])
    jid=c.post(db,'fee-reversal:'+r['business_reference'],'FEE_REVERSAL',p['currency'],
       [(fees['id'],r['amount_minor']),(payable['id'],-r['amount_minor'])],r['evidence_ref'],p['payout_id'],original['journal_id'])
    c.run(db,'UPDATE fee_reversal_reviews SET approver=:user,approved_at=now(),journal_id=:journal WHERE id=:id',user=user,journal=jid,id=review)
    c.audit(db,user,'APPROVE_FEE_REVERSAL',jid,r['evidence_ref'])
    return dict(journal_id=str(jid))


def make_router(require_role,get_db):
    router=APIRouter(dependencies=[Depends(require_role('admin'))])
    templates=Jinja2Templates(directory='templates')

    @router.get('/admin/earnings')
    def page(request: Request):
        return templates.TemplateResponse(request=request,name='earnings.html',context={'request':request})

    @router.get('/admin/api/earnings')
    def report(f=Depends(filters),db=Depends(get_db)):
        # A single snapshot for all aggregates in this response.
        c.run(db,'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        rows=partners(db,f)
        trend=c.run(db,f'''SELECT (posted_at AT TIME ZONE :timezone)::date AS day,
           sum(CASE WHEN event_type='PAYOUT' THEN amount_minor ELSE -amount_minor END) net_minor
           FROM fee_financial_events WHERE {EVENT_SCOPE} AND posted_at>=:start AND posted_at<:end
           GROUP BY day ORDER BY day''',**f).mappings().all()
        return dict(summary=summary(db,f),partners=[{**r,**{k:money(r[k]) for k in ('gross','reversals','net','pending')}} for r in rows],
           trend=[dict(day=str(r['day']),net=money(r['net_minor'])) for r in trend],
           partners_limit=100,partners_offset=0)

    @router.get('/admin/api/earnings/partners')
    def partner_report(f=Depends(filters),limit: int=Query(100,ge=1,le=200),offset: int=Query(0,ge=0),db=Depends(get_db)):
        return dict(items=[{**r,**{k:money(r[k]) for k in ('gross','reversals','net','pending')}} for r in partners(db,f,limit,offset)],limit=limit,offset=offset)

    @router.get('/admin/api/earnings/details')
    def detail_report(f=Depends(filters),limit: int=Query(50,ge=1,le=200),offset: int=Query(0,ge=0),sort: str='accepted_desc',state: str|None=None,db=Depends(get_db)):
        c.run(db,'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        return details(db,f,limit,offset,sort,state)

    @router.get('/admin/api/earnings/export.csv')
    def export(f=Depends(filters),sort: str='accepted_desc',state: str|None=None,db=Depends(get_db)):
        # Dedicated transaction is held throughout streaming, preventing page drift.
        c.run(db,'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        first=details(db,f,200,0,sort,state)
        columns=['partner','partner_id','payout_id','external_reference','stored_reference','principal','currency','original_fee','policy_version',
          'activity','payout_state','fee_state','recognized_at','reversed','reversed_at','gross_earned','net',
          'period_gross','period_reversals','period_net','pending_fee','evidence_state','financial_events']
        def safe(value):
            if isinstance(value,(list,dict)):
                return c.canonical(value)
            value='' if value is None else str(value)
            return "'"+value if value.startswith(('=','+','-','@','\t','\r')) else value
        def stream():
            buf=io.StringIO(); writer=csv.writer(buf);writer.writerow(columns)
            yield buf.getvalue();buf.seek(0);buf.truncate(0)
            offset=0;page=first
            while page['items']:
                for row in page['items']:
                    writer.writerow([safe(row.get(k)) for k in columns])
                yield buf.getvalue();buf.seek(0);buf.truncate(0)
                offset+=len(page['items'])
                if offset>=first['total']:
                    break
                page=details(db,f,200,offset,sort,state)
        return StreamingResponse(stream(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="fee-audit.csv"','Cache-Control':'no-store'})

    @router.post('/admin/api/earnings/reversals/propose')
    def proposal(body: Reversal,auth=Depends(require_role('admin')),db=Depends(get_db)):
        result=propose(db,body,auth['uid']);db.commit();return result

    @router.post('/admin/api/earnings/reversals/{review_id}/approve')
    def approval(review_id: UUID,auth=Depends(require_role('admin')),db=Depends(get_db)):
        result=approve(db,review_id,auth['uid']);db.commit();return result

    return router
