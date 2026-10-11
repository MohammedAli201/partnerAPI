"""Link the real SMS substitute to an admitted payout exactly once."""
from alembic import op

revision = '20261011_000013'
down_revision = '20261011_000012'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE phone_sms_jobs ADD COLUMN payout_id uuid UNIQUE REFERENCES payouts(id)')


def downgrade():
    raise RuntimeError('Preserve payment-to-SMS execution evidence with a reviewed restore')
