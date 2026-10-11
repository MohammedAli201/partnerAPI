"""Durable real SMS diagnostic queue, separate from payout accounting."""
from alembic import op

revision = '20261011_000012'
down_revision = '20261011_000011'
branch_labels = None
depends_on = None


def upgrade():
    op.get_bind().exec_driver_sql('''
    CREATE TABLE phone_sms_batches (
      id uuid PRIMARY KEY, request_id uuid NOT NULL UNIQUE,
      device_id uuid NOT NULL REFERENCES phone_worker_credentials(device_id),
      recipient text NOT NULL, count integer NOT NULL CHECK(count BETWEEN 1 AND 10),
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE phone_sms_jobs (
      id uuid PRIMARY KEY, batch_id uuid NOT NULL REFERENCES phone_sms_batches(id),
      device_id uuid NOT NULL REFERENCES phone_worker_credentials(device_id),
      ordinal integer NOT NULL, recipient text NOT NULL, message text NOT NULL,
      status text NOT NULL DEFAULT 'QUEUED' CHECK(status IN ('QUEUED','ASSIGNED','SENDING','SENT','FAILED','UNKNOWN')),
      lease_id uuid, lease_until timestamptz, subscription_id integer,
      result_code integer, detail text, delivery text,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(batch_id,ordinal)
    );
    CREATE UNIQUE INDEX phone_sms_one_active ON phone_sms_jobs(device_id)
      WHERE status IN ('ASSIGNED','SENDING','UNKNOWN');
    DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='partner_payout_runtime') THEN
        GRANT SELECT,INSERT,UPDATE ON phone_sms_batches,phone_sms_jobs TO partner_payout_runtime;
      END IF;
    END $$;
    ''')


def downgrade():
    raise RuntimeError('Preserve real SMS send evidence with a reviewed restore')
