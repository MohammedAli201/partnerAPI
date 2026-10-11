"""Persist Android worker credentials and delivery state alongside existing payouts."""
from alembic import op

revision = '20261010_000009'
down_revision = '20261009_000008'
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().exec_driver_sql('''
    CREATE TABLE phone_enrollment_codes (
      code_hash text PRIMARY KEY, device_id uuid NOT NULL REFERENCES payout_devices(id),
      expires_at timestamptz NOT NULL, used_at timestamptz,
      created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE phone_worker_credentials (
      device_id uuid PRIMARY KEY REFERENCES payout_devices(id), public_key text NOT NULL,
      access_hash text NOT NULL UNIQUE, refresh_hash text NOT NULL UNIQUE,
      access_expires_at timestamptz NOT NULL, refresh_expires_at timestamptz NOT NULL,
      paused boolean NOT NULL DEFAULT false, drain boolean NOT NULL DEFAULT false,
      revoked boolean NOT NULL DEFAULT false, last_seen_at timestamptz, state text,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE phone_worker_assignments (
      attempt_id uuid PRIMARY KEY REFERENCES payout_attempts(id),
      device_id uuid NOT NULL REFERENCES phone_worker_credentials(device_id),
      payload jsonb NOT NULL, phase text NOT NULL DEFAULT 'QUEUED',
      sequence bigint NOT NULL DEFAULT 0 CHECK(sequence>=0), acked boolean NOT NULL DEFAULT false,
      authorization_id uuid UNIQUE, authorization_expires_at timestamptz,
      scenario text NOT NULL DEFAULT 'SUCCESS', created_at timestamptz NOT NULL DEFAULT now(),
      CHECK((authorization_id IS NULL)=(authorization_expires_at IS NULL))
    );
    CREATE TABLE phone_worker_events (
      event_id uuid PRIMARY KEY, attempt_id uuid NOT NULL REFERENCES phone_worker_assignments(attempt_id),
      sequence bigint NOT NULL CHECK(sequence>0), payload_hash text NOT NULL, payload jsonb NOT NULL,
      received_at timestamptz NOT NULL DEFAULT now(), UNIQUE(attempt_id,sequence)
    );
    DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='partner_payout_runtime') THEN
        GRANT SELECT,INSERT,UPDATE ON phone_enrollment_codes,phone_worker_credentials,phone_worker_assignments
          TO partner_payout_runtime;
        GRANT SELECT,INSERT ON phone_worker_events TO partner_payout_runtime;
      END IF;
    END $$;
    ''')


def downgrade():
    raise RuntimeError('Worker execution evidence requires a reviewed restore, not deletion')
