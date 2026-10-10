"""Store public partnership enquiries separately from payout records."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision='20261009_000008'
down_revision='20261009_000007'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('public_partnership_enquiries',
        sa.Column('id',postgresql.UUID(as_uuid=True),primary_key=True),
        sa.Column('reference',sa.String(32),nullable=False,unique=True),
        sa.Column('payload_hash',sa.String(64),nullable=False),
        sa.Column('company_name',sa.String(160),nullable=False),
        sa.Column('country',sa.String(100),nullable=False),
        sa.Column('contact_name',sa.String(100),nullable=False),
        sa.Column('email',sa.String(254),nullable=False),
        sa.Column('monthly_volume',sa.String(64),nullable=False),
        sa.Column('channels',sa.String(64),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
    )
    op.create_index('ix_public_partnership_enquiries_created','public_partnership_enquiries',['created_at','id'])

def downgrade():
    op.drop_table('public_partnership_enquiries')
