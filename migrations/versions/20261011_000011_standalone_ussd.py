"""Allow real SIM diagnostics without a simulated payout."""
from alembic import op

revision = '20261011_000011'
down_revision = '20261010_000010'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE phone_ussd_tests ALTER COLUMN attempt_id DROP NOT NULL')
    op.execute('ALTER TABLE phone_ussd_tests ADD COLUMN request_id uuid')
    op.execute('CREATE UNIQUE INDEX phone_ussd_request ON phone_ussd_tests(device_id,request_id)')


def downgrade():
    raise RuntimeError('Preserve actual carrier diagnostic evidence with a reviewed restore')
