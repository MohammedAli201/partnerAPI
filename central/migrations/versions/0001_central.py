"""Create central source of truth; shared with the legacy upgrade chain."""
from pathlib import Path
from alembic import op

revision='central_0001'
down_revision=None
branch_labels=None
depends_on=None


def upgrade():
    if op.get_bind().dialect.has_schema(op.get_bind(),'central'):
        # Avoid silently stamping an unknown/pre-existing central schema.
        raise RuntimeError('central schema already exists; use its original migration chain')
    op.get_bind().exec_driver_sql((Path(__file__).resolve().parents[2]/'schema.sql').read_text(encoding='utf-8'))


def downgrade():
    raise RuntimeError('No destructive financial downgrade')
