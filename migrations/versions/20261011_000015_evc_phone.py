"""Bind real EVC phone execution and carrier-response evidence to existing payouts."""
from alembic import op

revision = '20261011_000015'
down_revision = '20261011_000014'
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().exec_driver_sql('''
    CREATE TABLE phone_evc_settings (
      device_id uuid PRIMARY KEY REFERENCES phone_worker_credentials(device_id),
      sim_subscription_id integer NOT NULL CHECK(sim_subscription_id>=0),
      enabled boolean NOT NULL DEFAULT true, float_known boolean NOT NULL DEFAULT false,
      configured_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE phone_evc_confirmations (
      attempt_id uuid PRIMARY KEY REFERENCES payout_attempts(id),
      event_id uuid NOT NULL UNIQUE REFERENCES phone_worker_events(event_id),
      payout_id uuid NOT NULL UNIQUE REFERENCES payouts(id),
      wallet_id uuid NOT NULL REFERENCES payout_wallets(id), response_hash text NOT NULL,
      recipient text NOT NULL, recipient_name text NOT NULL, amount_minor bigint NOT NULL CHECK(amount_minor>0),
      remaining_minor bigint NOT NULL CHECK(remaining_minor>=0), carrier_at timestamptz NOT NULL,
      response_text text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(wallet_id,response_hash)
    );
    DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='partner_payout_runtime') THEN
        GRANT SELECT,INSERT,UPDATE ON phone_evc_settings TO partner_payout_runtime;
        GRANT SELECT,INSERT ON phone_evc_confirmations TO partner_payout_runtime;
      END IF;
    END $$;
    ''')
    # Preserve both existing settlement evidence paths and add an explicitly typed
    # device/carrier-response path. No fabricated carrier receipt/reference.
    op.get_bind().exec_driver_sql('''CREATE OR REPLACE FUNCTION payment_settlement_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.status IS DISTINCT FROM NEW.status AND NEW.canonical_hash IS NOT NULL THEN
        IF NEW.status_version<>OLD.status_version+1 OR NOT EXISTS(
          SELECT 1 FROM payout_history WHERE payout_id=NEW.id AND version=NEW.status_version AND new_status=NEW.status)
        THEN RAISE EXCEPTION 'Status transition requires matching durable history'; END IF;
        IF NEW.status='SENT' AND (
          NOT EXISTS(SELECT 1 FROM ledger_journals WHERE payout_id=NEW.id AND event_type='PAYOUT') OR
          (NOT EXISTS(SELECT 1 FROM provider_receipts WHERE payout_id=NEW.id) AND NOT EXISTS(
            SELECT 1 FROM phone_sms_jobs j JOIN payout_fee_snapshots s ON s.payout_id=j.payout_id
            JOIN ledger_journals l ON l.payout_id=j.payout_id
            WHERE j.payout_id=NEW.id AND j.status='SENT' AND j.result_code=-1
              AND s.activity='simulation' AND NEW.request_payload::jsonb->>'sms_test_accounting'='true'
              AND l.business_event_key='sms-test-payout:'||NEW.id::text
              AND l.evidence_ref='sms-test:'||j.id::text||':android-result-ok') AND NOT EXISTS(
            SELECT 1 FROM phone_evc_confirmations r JOIN phone_worker_events e ON e.event_id=r.event_id
            JOIN payout_attempts a ON a.id=r.attempt_id JOIN ledger_journals l ON l.payout_id=r.payout_id
            WHERE r.payout_id=NEW.id AND a.phase='SUCCESS' AND a.resolved_at IS NOT NULL
              AND a.wallet_id=r.wallet_id AND NEW.request_payload::jsonb->>'evc_auto_payment'='true'
              AND e.payload->>'phase'='CONFIRMED_SUCCESS'
              AND l.business_event_key='evc-payout:'||NEW.id::text
              AND l.evidence_ref='android-ussd-event:'||r.event_id::text)) OR
          NOT EXISTS(SELECT 1 FROM payout_reservations WHERE payout_id=NEW.id AND status='CAPTURED') OR
          NOT EXISTS(SELECT 1 FROM payout_webhook_events WHERE payout_id=NEW.id AND status_version=NEW.status_version))
        THEN RAISE EXCEPTION 'Settlement requires journal, typed payment evidence, capture and outbox'; END IF;
      END IF;
      RETURN NULL;
    END $$''')


def downgrade():
    raise RuntimeError('Keep real EVC execution evidence; use a reviewed restore')
