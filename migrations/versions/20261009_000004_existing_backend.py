"""Harden existing partner/payout records, without copying them to central."""
from pathlib import Path
from alembic import op

revision='20261009_000004'
down_revision='20261009_000003'
branch_labels=None
depends_on=None

def upgrade():
    op.get_bind().exec_driver_sql((Path(__file__).resolve().parents[2]/'hardening.sql').read_text(encoding='utf-8'))

def downgrade():
    raise RuntimeError('Financial/evidence migration requires a reviewed restore, not destructive downgrade')
