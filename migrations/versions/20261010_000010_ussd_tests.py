"""Record operator-triggered USSD diagnostics separately from payment evidence."""
from alembic import op

revision = '20261010_000010'
down_revision = '20261010_000009'
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().exec_driver_sql('''
    CREATE TABLE phone_ussd_tests (
      id uuid PRIMARY KEY, attempt_id uuid NOT NULL UNIQUE REFERENCES phone_worker_assignments(attempt_id),
      device_id uuid NOT NULL REFERENCES phone_worker_credentials(device_id), command text NOT NULL,
      status text NOT NULL DEFAULT 'CREATED' CHECK(status IN ('CREATED','REQUESTED','RESPONDED','FAILED','UNKNOWN')),
      response text, expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    );
    DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='partner_payout_runtime') THEN
        GRANT SELECT,INSERT,UPDATE ON phone_ussd_tests TO partner_payout_runtime;
      END IF;
    END $$;
    ''')


def downgrade():
    raise RuntimeError('USSD diagnostic evidence requires a reviewed restore')
