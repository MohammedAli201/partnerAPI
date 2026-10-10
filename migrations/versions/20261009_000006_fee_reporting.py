"""Immutable historical fee snapshots; reports remain based on financial entries."""
from alembic import op
revision='20261009_000006'
down_revision='20261009_000005'
branch_labels=None
depends_on=None

def upgrade():
    op.get_bind().exec_driver_sql('''
    CREATE TABLE payout_fee_snapshots (
      payout_id uuid PRIMARY KEY REFERENCES payouts(id), partner_id integer NOT NULL REFERENCES partners(id),
      currency text NOT NULL, fee_minor bigint NOT NULL CHECK(fee_minor>=0),
      policy_version text NOT NULL, components jsonb NOT NULL,
      activity text NOT NULL CHECK(activity IN ('live','simulation','unclassified')),
      evidence_state text NOT NULL, accepted_at timestamptz NOT NULL
    );
    INSERT INTO payout_fee_snapshots
    SELECT p.id,p.partner_id,p.currency,(r.fee*100)::bigint,'legacy-success-v1',
      jsonb_build_object('type','historical-snapshot','amount_minor',(r.fee*100)::bigint),
      CASE WHEN to_regclass('public.simulation_marker') IS NOT NULL OR EXISTS(
        SELECT 1 FROM payout_attempts a JOIN payment_workers w ON w.id=a.worker_id WHERE a.payout_id=p.id AND w.simulator
      ) THEN 'simulation' WHEN EXISTS(
        SELECT 1 FROM payout_attempts a JOIN payment_workers w ON w.id=a.worker_id WHERE a.payout_id=p.id AND NOT w.simulator
      ) THEN 'live' ELSE 'unclassified' END,
      CASE WHEN p.status='SENT' AND NOT EXISTS(
        SELECT 1 FROM ledger_journals j JOIN ledger_entries e ON e.journal_id=j.id
        JOIN ledger_accounts a ON a.id=e.account_id WHERE j.payout_id=p.id AND j.event_type='PAYOUT'
        AND a.kind='FEES' AND -e.amount_minor=(r.fee*100)::bigint
      ) AND r.fee<>0 THEN 'RECONCILIATION_REQUIRED' ELSE 'RESERVATION_SNAPSHOT' END,r.created_at
    FROM payouts p JOIN payout_reservations r ON r.payout_id=p.id
    WHERE r.fee>=0 AND r.fee*100=trunc(r.fee*100) AND p.currency IN ('USD','EUR','GBP');
    CREATE TRIGGER fee_snapshot_immutable BEFORE UPDATE OR DELETE ON payout_fee_snapshots
      FOR EACH ROW EXECUTE FUNCTION payment_immutable();
    CREATE INDEX fee_snapshot_scope ON payout_fee_snapshots(activity,currency,partner_id,payout_id);
    CREATE INDEX financial_posting_report ON ledger_journals(posted_at,payout_id) WHERE event_type IN ('PAYOUT','FEE_REVERSAL');
    CREATE INDEX financial_fee_entries ON ledger_entries(account_id,journal_id);
    CREATE TABLE fee_reversal_reviews (
      id uuid PRIMARY KEY, payout_id uuid NOT NULL REFERENCES payout_fee_snapshots(payout_id),
      business_reference text NOT NULL UNIQUE, amount_minor bigint NOT NULL CHECK(amount_minor>0),
      reason text NOT NULL, evidence_ref text NOT NULL,
      proposer integer NOT NULL REFERENCES users(id), approver integer REFERENCES users(id),
      created_at timestamptz NOT NULL DEFAULT now(), approved_at timestamptz,
      journal_id uuid UNIQUE REFERENCES ledger_journals(id), CHECK(approver IS NULL OR approver<>proposer)
    );
    CREATE VIEW fee_financial_events AS
      SELECT j.id AS journal_id,j.business_event_key,j.payout_id,j.posted_at,j.reversal_of,j.evidence_ref,
        s.partner_id,s.currency,s.activity,j.event_type,
        CASE WHEN j.event_type='PAYOUT' THEN -e.amount_minor ELSE e.amount_minor END AS amount_minor
      FROM ledger_journals j JOIN ledger_entries e ON e.journal_id=j.id
      JOIN ledger_accounts a ON a.id=e.account_id AND a.kind='FEES'
      JOIN payout_fee_snapshots s ON s.payout_id=j.payout_id
      WHERE (j.event_type='PAYOUT' AND e.amount_minor<0)
         OR (j.event_type='FEE_REVERSAL' AND e.amount_minor>0 AND j.reversal_of IS NOT NULL);
    DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='partner_payout_runtime') THEN
      GRANT SELECT,INSERT ON payout_fee_snapshots TO partner_payout_runtime;
      GRANT SELECT ON fee_financial_events TO partner_payout_runtime;
      GRANT SELECT,INSERT,UPDATE ON fee_reversal_reviews TO partner_payout_runtime;
    END IF; END $$;
    ''')

def downgrade():
    raise RuntimeError('Fee evidence and compensating financial history must be preserved')
