"""Persist signed callback bodies and delivery acknowledgements."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260915_000002"
down_revision = "20260423_000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payout_webhook_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("payout_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payouts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("callback_url", sa.Text(), nullable=False),
        sa.Column("raw_body", sa.LargeBinary(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("last_status_code", sa.Integer()),
        sa.Column("last_error", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payout_webhook_events_due", "payout_webhook_events", ["accepted_at", "next_attempt_at"])


def downgrade():
    op.drop_table("payout_webhook_events")
