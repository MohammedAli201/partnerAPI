"""Separate physical execution containment from unresolved financial evidence."""
from alembic import op
revision='20261009_000005'
down_revision='20261009_000004'
branch_labels=None
depends_on=None

def upgrade():
    op.get_bind().exec_driver_sql('''
    ALTER TABLE payout_attempts ADD COLUMN execution_closed_at timestamptz;
    DROP INDEX unresolved_device;
    DROP INDEX unresolved_wallet;
    CREATE UNIQUE INDEX unresolved_device ON payout_attempts(device_id) WHERE resolved_at IS NULL AND execution_closed_at IS NULL;
    CREATE UNIQUE INDEX unresolved_wallet ON payout_attempts(wallet_id) WHERE resolved_at IS NULL AND execution_closed_at IS NULL;
    CREATE TABLE execution_containment_reviews (
      id uuid PRIMARY KEY, attempt_id uuid NOT NULL UNIQUE REFERENCES payout_attempts(id),
      observed_minor bigint NOT NULL CHECK(observed_minor>=0), evidence_ref text NOT NULL,
      proposer integer NOT NULL REFERENCES users(id), approver integer REFERENCES users(id),
      approved_at timestamptz, CHECK(approver IS NULL OR approver<>proposer)
    );
    CREATE FUNCTION payment_containment_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
     IF OLD.execution_closed_at IS NOT NULL AND NEW.execution_closed_at IS DISTINCT FROM OLD.execution_closed_at
     THEN RAISE EXCEPTION 'Physical containment cannot be undone'; END IF;
     IF OLD.execution_closed_at IS NULL AND NEW.execution_closed_at IS NOT NULL AND NOT EXISTS(
       SELECT 1 FROM execution_containment_reviews WHERE attempt_id=NEW.id AND approved_at IS NOT NULL)
     THEN RAISE EXCEPTION 'Independent physical containment approval required'; END IF;
     RETURN NEW;
    END $$;
    CREATE TRIGGER guarded_execution_containment BEFORE UPDATE ON payout_attempts FOR EACH ROW EXECUTE FUNCTION payment_containment_guard();
    DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='partner_payout_runtime') THEN
        GRANT SELECT,INSERT,UPDATE ON execution_containment_reviews TO partner_payout_runtime;
      END IF;
    END $$;
    ''')

def downgrade():
    raise RuntimeError('Containment evidence cannot be discarded by downgrade')
