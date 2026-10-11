"""Allow explicitly classified SMS test accounting without a carrier payment receipt."""
from alembic import op

revision = '20261011_000014'
down_revision = '20261011_000013'
branch_labels = None
depends_on = None


def upgrade():
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
              AND l.evidence_ref='sms-test:'||j.id::text||':android-result-ok')) OR
          NOT EXISTS(SELECT 1 FROM payout_reservations WHERE payout_id=NEW.id AND status='CAPTURED') OR
          NOT EXISTS(SELECT 1 FROM payout_webhook_events WHERE payout_id=NEW.id AND status_version=NEW.status_version))
        THEN RAISE EXCEPTION 'Settlement requires journal, receipt or classified SMS test, capture and outbox'; END IF;
      END IF;
      RETURN NULL;
    END $$''')


def downgrade():
    raise RuntimeError('Preserve SMS test accounting evidence with a reviewed restore')
