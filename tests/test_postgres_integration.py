"""Migration conservation regression; execution regressions live in test_existing_backend."""
from test_existing_backend import pg,setup
import backend_core as c
import os
from pathlib import Path
from uuid import uuid4
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config

def test_legacy_balances_remain_identified_openings(pg,setup):
    with pg.begin() as db:
        partner=c.row(db,'SELECT * FROM partners WHERE id=:id',id=setup['partner'])
        assert partner['balance_available']==1000 and partner['balance_reserved']==0
        assert partner['ledger_enabled'] is True
        journals=c.run(db,"SELECT event_type,evidence_ref FROM ledger_journals WHERE business_event_key LIKE 'opening:%'").mappings().all()
        assert journals and all(j['event_type']=='OPENING' for j in journals)
        assert all(j['evidence_ref']=='bank://reconciled-opening' for j in journals)
        assert c.row(db,'SELECT count(*) AS n FROM ledger_entries')['n']>=4


def test_upgrade_preserves_legacy_money_and_holds_execution(monkeypatch):
    url=os.getenv('CENTRAL_TEST_CLUSTER_URL')
    if not url: pytest.skip('Explicit disposable PostgreSQL required')
    name='migration_test_'+uuid4().hex
    cluster=create_engine(url,isolation_level='AUTOCOMMIT')
    with cluster.connect() as db: db.exec_driver_sql(f'CREATE DATABASE {name}')
    dburl=make_url(url).set(database=name)
    engine=create_engine(dburl)
    cfg=Config('alembic.ini')
    monkeypatch.setenv('TEST_DATABASE_URL',dburl.render_as_string(hide_password=False))
    try:
        command.upgrade(cfg,'20260915_000002')
        payout=uuid4()
        with engine.begin() as db:
            partner=c.row(db,"INSERT INTO partners(name,api_key_prefix,api_key_hash,balance_available,balance_reserved) VALUES('Legacy','abcdefgh','legacy',89.40,10.60) RETURNING id")['id']
            c.run(db,"INSERT INTO payouts(id,partner_id,partner_tx_id,amount,currency,recipient,provider,status,request_payload) VALUES(:id,:partner,:reference,10,'USD','+252611234567','Hormuud','PROCESSING',:payload)",id=payout,partner=partner,reference='pm_260101-ABC123_'+str(uuid4()),payload='{"payout_channel":"evc"}')
            c.run(db,"INSERT INTO payout_reservations(payout_id,partner_id,amount,fee,total) VALUES(:id,:partner,10,.60,10.60)",id=payout,partner=partner)
            c.run(db,"INSERT INTO payout_queue(payout_id,status,worker_id,lease_until) VALUES(:id,'IN_PROGRESS','old-phone',now()+interval '1 hour')",id=payout)
            c.run(db,"INSERT INTO balance_transactions(partner_id,type,amount,previous_balance,new_balance,reference) VALUES(:partner,'deposit',100,0,100,'legacy-bank-ref')",partner=partner)
        command.upgrade(cfg,'head')
        with engine.begin() as db:
            p=c.row(db,'SELECT * FROM partners WHERE id=:id',id=partner)
            assert p['balance_available']==Decimal('89.40') and p['balance_reserved']==Decimal('10.60')
            assert not p['ledger_enabled']
            assert c.row(db,'SELECT * FROM payouts')['status']=='UNKNOWN'
            assert c.row(db,'SELECT * FROM payout_queue')['status']=='HELD'
            assert c.row(db,'SELECT * FROM payout_reservations')['status']=='ACTIVE'
            assert c.row(db,'SELECT * FROM balance_transactions')['reference']=='legacy-bank-ref'
            assert c.row(db,'SELECT count(*) AS n FROM ledger_journals')['n']==0
            assert c.row(db,'SELECT count(*) AS n FROM reconciliation_cases')['n']==1
    finally:
        engine.dispose()
        with cluster.connect() as db: db.exec_driver_sql(f'DROP DATABASE {name} WITH (FORCE)')
        cluster.dispose()


def test_restricted_runtime_posts_without_history_edit_rights(pg,setup):
    role='payout_role_'+uuid4().hex
    sql=Path('payment_roles.sql').read_text(encoding='utf-8').replace('partner_payout_runtime',role)
    with pg.begin() as db: db.exec_driver_sql(sql)
    try:
        with pg.begin() as db:
            db.exec_driver_sql('SET LOCAL ROLE '+role)
            result=c.deposit(db,setup['partner'],'1.00','runtime-test','bank://verified','test')
            assert result
        with pytest.raises(Exception,match='permission denied'):
            with pg.begin() as db:
                db.exec_driver_sql('SET LOCAL ROLE '+role)
                c.run(db,'UPDATE ledger_accounts SET balance_minor=0')
        with pytest.raises(Exception,match='permission denied'):
            with pg.begin() as db:
                db.exec_driver_sql('SET LOCAL ROLE '+role)
                c.run(db,'DELETE FROM ledger_entries')
    finally:
        with pg.begin() as db:
            db.exec_driver_sql('DROP OWNED BY '+role)
            db.exec_driver_sql('DROP ROLE '+role)
