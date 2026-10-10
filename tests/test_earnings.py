from datetime import date,datetime,timezone
from decimal import Decimal
from uuid import UUID,uuid4
import csv
import io
import pytest
from fastapi import HTTPException
from sqlalchemy import text
import backend_core as c
import payment_worker as w
import earnings as e
from test_existing_backend import pg,setup,submit,payload,claim,arm,report
from test_existing_http import client


def scope(**changes):
    return {**e.period('month'),'currency':'USD','activity':'simulation','partner':None,**changes}


def success(pg,setup,amount='100.00',fee='0.60',currency='USD'):
    p=payload(amount=amount,currency=currency)
    with pg.begin() as db:
        accepted=c.admission(db,setup['partner'],p,p.partner_tx_id,None,Decimal(fee))
    command=claim(pg,setup);arm(pg,setup,command)
    result=report(command)
    with pg.begin() as db:
        w.result(db,setup['worker'],result)
        w.result(db,setup['worker'],result)
    return accepted


def reverse(pg,setup,payout,amount,reference=None):
    body=e.Reversal(payout_id=payout,amount_minor=amount,business_reference=reference or str(uuid4()),reason='Agreed partner fee refund',evidence_ref='review://fee-refund')
    with pg.begin() as db:
        rid=e.propose(db,body,setup['admins'][0]['id'])['review_id']
    with pg.begin() as db:
        return e.approve(db,UUID(rid),setup['admins'][1]['id'])


def test_recognition_holds_failure_unknown_and_duplicate(pg,setup):
    accepted=submit(pg,setup,payload(amount='100.00'))
    with pg.begin() as db:
        assert c.run(db,'SELECT balance_reserved FROM partners WHERE id=:id',id=setup['partner']).scalar()==Decimal('100.60')
        s=e.summary(db,scope());assert (s['gross'],s['pending'])==('0.00','0.60')
    cmd=claim(pg,setup);arm(pg,setup,cmd);result=report(cmd)
    with pg.begin() as db:
        w.result(db,setup['worker'],result);w.result(db,setup['worker'],result)
        s=e.summary(db,scope());assert (s['net'],s['pending'])==('0.60','0.00')
        assert c.run(db,"SELECT count(*) FROM fee_financial_events WHERE event_type='PAYOUT'").scalar()==1
    submit(pg,setup);cmd=claim(pg,setup)
    failure={**report(cmd),'outcome':'DEFINITE_FAILURE_BEFORE_SEND','stage':'BEFORE_ARM','proof':None,'provider_reference':None}
    with pg.begin() as db:
        w.result(db,setup['worker'],failure)
        assert e.summary(db,scope())['pending']=='0.00'
    submit(pg,setup);cmd=claim(pg,setup);arm(pg,setup,cmd)
    with pg.begin() as db:
        w.result(db,setup['worker'],{**report(cmd),'outcome':'UNKNOWN','proof':None,'provider_reference':None})
        s=e.summary(db,scope());assert (s['net'],s['pending'])==('0.60','0.60')
    reverse(pg,setup,accepted['id'],60)
    with pg.begin() as db:
        s=e.summary(db,scope());assert (s['gross'],s['reversals'],s['net'])==('0.60','0.60','0.00')


def test_partial_reversals_policy_history_and_period(pg,setup,monkeypatch):
    monkeypatch.setenv('FEE_POLICY_VERSION','fixed-price-2026-a')
    a=success(pg,setup)
    monkeypatch.setenv('FEE_POLICY_VERSION','fixed-price-2026-b')
    b=success(pg,setup,fee='1.25')
    reference=str(uuid4());reverse(pg,setup,a['id'],20,reference)
    reverse(pg,setup,a['id'],20,reference)
    with pg.begin() as db:
        s=e.summary(db,scope());assert (s['gross'],s['reversals'],s['net'])==('1.85','0.20','1.65')
        snapshots=c.run(db,'SELECT fee_minor FROM payout_fee_snapshots ORDER BY fee_minor').scalars().all()
        assert snapshots==[60,125]
        versions=c.run(db,'SELECT policy_version FROM payout_fee_snapshots ORDER BY fee_minor').scalars().all()
        assert versions==['fixed-price-2026-a','fixed-price-2026-b']
        assert e.summary(db,scope(activity='live'))['net']=='0.00'
        assert e.summary(db,scope(currency='EUR'))['net']=='0.00'
        assert e.summary(db,scope(partner=999999))['net']=='0.00'
    reverse(pg,setup,a['id'],40)
    with pytest.raises(HTTPException):
        reverse(pg,setup,a['id'],1)
    with pg.begin() as db:
        # Period bounds isolate the original posting from subsequent compensations.
        original=c.run(db,"SELECT posted_at FROM ledger_journals WHERE payout_id=:id AND event_type='PAYOUT'",id=a['id']).scalar()
        reversal=c.run(db,"SELECT min(posted_at) FROM ledger_journals WHERE payout_id=:id AND event_type='FEE_REVERSAL'",id=a['id']).scalar()
        s=e.summary(db,scope(start=reversal,partner=setup['partner']))
        assert s['gross']=='0.00' and s['reversals']=='0.60' and s['net']=='-0.60'
        assert original<reversal


def test_timezone_calendar_boundaries(monkeypatch):
    monkeypatch.setenv('REPORTING_TIMEZONE','Europe/Oslo')
    p=e.period('today',now=datetime(2026,3,29,12,tzinfo=timezone.utc))
    assert p['start']==datetime(2026,3,28,23,tzinfo=timezone.utc)
    assert p['end']==datetime(2026,3,29,22,tzinfo=timezone.utc)
    p=e.period('custom',date(2026,10,25),date(2026,10,25))
    assert (p['end']-p['start']).total_seconds()==25*3600


def test_database_rejects_snapshot_edits_and_unapproved_compensation(pg,setup):
    from sqlalchemy.exc import SQLAlchemyError
    a=success(pg,setup)
    with pytest.raises(SQLAlchemyError):
        with pg.begin() as db:
            c.run(db,'UPDATE payout_fee_snapshots SET fee_minor=125 WHERE payout_id=:id',id=a['id'])
    with pytest.raises(SQLAlchemyError):
        with pg.begin() as db:
            original=c.row(db,"SELECT * FROM fee_financial_events WHERE payout_id=:id",id=a['id'])
            fees=c.account(db,'fees:USD','FEES','USD');payable=c.funding_account(db,setup['partner'],'USD')
            c.post(db,'unauthorized-compensation','FEE_REVERSAL','USD',[(fees['id'],20),(payable['id'],-20)],
              'review://missing-approval',UUID(a['id']),original['journal_id'])
    with pg.begin() as db:
        assert e.summary(db,scope())['net']=='0.60'


def test_admin_report_detail_export_and_security(pg,setup,client):
    http,main=client
    from sqlalchemy.exc import SQLAlchemyError
    async def show_test_error(request,error):
        raise error
    main.app.exception_handlers[SQLAlchemyError]=show_test_error
    a=success(pg,setup);reverse(pg,setup,a['id'],20)
    assert http.get('/admin/api/earnings').status_code==401
    from browser_security import create
    with pg.begin() as db:
        token,csrf=create(db,setup['admins'][0]['id'],main.settings.secret_key)
    http.cookies.set('session',token);http.cookies.set('csrf_token',csrf)
    q='?activity=simulation&currency=USD&preset=month'
    assert http.get('/admin/earnings').status_code==200
    r=http.get('/admin/api/earnings'+q);assert r.status_code==200,r.text
    s=r.json()['summary'];assert (s['gross'],s['reversals'],s['net'])==('0.60','0.20','0.40')
    assert r.json()['partners'][0]['net']=='0.40'
    d=http.get('/admin/api/earnings/details'+q).json()
    assert d['total']==1 and d['items'][0]['net']=='0.40' and d['items'][0]['fee_state']=='PARTIALLY_REVERSED'
    exported=http.get('/admin/api/earnings/export.csv'+q)
    assert exported.status_code==200,exported.text
    rows=list(csv.DictReader(io.StringIO(exported.text)));assert len(rows)==1 and rows[0]['net']=='0.40'
    assert rows[0]['period_net']==s['net'] and rows[0]['period_gross']==s['gross'] and rows[0]['period_reversals']==s['reversals']
    funds=http.get('/admin/api/funds/partners?earnings_activity=simulation').json()
    assert funds['partners'][0]['earned_fees']=='0.40'
    assert http.get('/admin/api/earnings?currency=ALL').status_code==422
    proposal=http.post('/admin/api/earnings/reversals/propose',json=dict(payout_id=a['id'],amount_minor=40,business_reference='ui-reversal',reason='Agreed partner fee refund',evidence_ref='review://new-refund'))
    assert proposal.status_code==403
    proposal=http.post('/admin/api/earnings/reversals/propose',headers={'X-CSRF-Token':csrf},json=dict(payout_id=a['id'],amount_minor=40,business_reference='ui-reversal',reason='Agreed partner fee refund',evidence_ref='review://new-refund'))
    assert proposal.status_code==200,proposal.text
    assert http.post('/admin/api/earnings/reversals/'+proposal.json()['review_id']+'/approve',headers={'X-CSRF-Token':csrf}).status_code==403
    with pg.begin() as db:
        c.run(db,"UPDATE users SET role='partner' WHERE id=:id",id=setup['admins'][0]['id'])
    assert http.get('/admin/api/earnings'+q).status_code==403
    assert http.get('/admin/api/earnings/export.csv'+q).status_code==403


def test_two_partner_two_currency_isolation(pg,setup):
    success(pg,setup)
    from security import generate_api_key
    key,prefix,verifier=generate_api_key()
    with pg.begin() as db:
        p=c.row(db,"INSERT INTO partners(name,api_key_prefix,api_key_hash,funding_currency,balance_available) VALUES('Euro Partner',:prefix,:hash,'EUR',1000) RETURNING *",prefix=prefix,hash=verifier)
        review=c.opening_propose(db,p['id'],setup['admins'][0]['id'],1000,0,'bank://euro-opening')
        c.opening_approve(db,review['review_id'],setup['admins'][1]['id'])
        wallet,device=uuid4(),uuid4()
        asset=c.account(db,f'wallet:{wallet}','WALLET','EUR');opening=c.account(db,'wallet-opening:EUR','OPENING','EUR')
        c.post(db,f'wallet-opening:{wallet}','OPENING','EUR',[(asset['id'],100000),(opening['id'],-100000)],'operator://euro-opening')
        c.run(db,"INSERT INTO payout_wallets VALUES(:id,:ref,'EUR',:account,true,100000,now())",id=wallet,ref=str(wallet),account=asset['id'])
        c.run(db,"INSERT INTO payout_devices VALUES(:id,:sim,:worker,:wallet,'Hormuud','evc',false,true)",id=device,sim=str(device),worker=setup['worker']['id'],wallet=wallet)
    other={**setup,'partner':p['id'],'device':device,'wallet':wallet}
    success(pg,other,fee='1.25',currency='EUR')
    with pg.begin() as db:
        assert e.summary(db,scope())['net']=='0.60'
        assert e.summary(db,scope(currency='EUR'))['net']=='1.25'
        assert e.summary(db,scope(partner=p['id']))['net']=='0.00'
        assert e.summary(db,scope(currency='EUR',partner=setup['partner']))['net']=='0.00'
        assert e.details(db,scope(currency='EUR'))['items'][0]['partner_id']==p['id']


def test_reversal_posted_in_later_month(pg,setup,monkeypatch):
    from datetime import timedelta
    monkeypatch.setenv('REPORTING_TIMEZONE','UTC')
    first=datetime.now(timezone.utc).replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    prior=first-timedelta(days=1)
    original_run=c.run
    def historical_fixture(db,sql,**params):
        if 'INSERT INTO ledger_journals' in sql and params.get('event')=='PAYOUT':
            sql=sql.replace('evidence_ref,reversal_of)','evidence_ref,reversal_of,posted_at)').replace(':evidence,:reversal)',':evidence,:reversal,:fixture_posted)')
            params['fixture_posted']=prior
        return original_run(db,sql,**params)
    monkeypatch.setattr(c,'run',historical_fixture)
    a=success(pg,setup)
    reverse(pg,setup,a['id'],60)
    with pg.begin() as db:
        s=e.summary(db,scope());assert (s['gross'],s['reversals'],s['net'])==('0.00','0.60','-0.60')
        old=scope(**e.period('custom',prior.date().replace(day=1),prior.date()))
        assert e.summary(db,old)['gross']=='0.60' and e.summary(db,old)['reversals']=='0.00'
        d=e.details(db,scope())['items'][0]
        assert d['period_net']=='-0.60' and d['net']=='0.00'
