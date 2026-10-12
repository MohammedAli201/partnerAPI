"""Retain all fields submitted by the supplied partner enquiry form."""
from alembic import op
revision='20261012_000016'
down_revision='20261011_000015'
branch_labels=None
depends_on=None

def upgrade():
    op.get_bind().exec_driver_sql("""ALTER TABLE public_partnership_enquiries
      ADD COLUMN business_type text,
      ADD COLUMN message text NOT NULL DEFAULT '',
      ADD COLUMN selected_channels jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK(jsonb_typeof(selected_channels)='array');""")

def downgrade():
    raise RuntimeError('Preserve submitted enquiry details; use a reviewed restore')
