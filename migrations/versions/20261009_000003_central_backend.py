"""Reserved revision from the superseded separate-service draft.

No production rollout occurred during this session. Keep the identifier so
previous local test databases can continue to revision 004, without installing
the unused central schema into newly upgraded partner databases. Any preexisting
central schema is retained, never dropped by this compatibility revision.
"""

revision = '20261009_000003'
down_revision = '20260915_000002'
branch_labels = None
depends_on = None

def upgrade():
    pass

def downgrade():
    pass
