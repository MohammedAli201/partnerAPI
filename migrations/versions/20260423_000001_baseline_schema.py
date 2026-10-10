"""baseline schema

Revision ID: 20260423_000001
Revises:
Create Date: 2026-04-23 00:00:01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260423_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "partners",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("api_key_prefix", sa.String(length=8), nullable=False),
        sa.Column("api_key_hash", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("balance_available", sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("balance_reserved", sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_partners_api_key_prefix", "partners", ["api_key_prefix"], unique=True)

    op.create_table(
        "payouts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("partner_id", sa.Integer(), nullable=False),
        sa.Column("partner_tx_id", sa.String(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default=sa.text("'USD'")),
        sa.Column("recipient", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'RECEIVED'")),
        sa.Column("request_payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("partner_id", "partner_tx_id", name="uq_payouts_partner_partner_tx_id"),
    )
    op.create_index("ix_payouts_created_at", "payouts", ["created_at"], unique=False)
    op.create_index("ix_payouts_partner_id", "payouts", ["partner_id"], unique=False)
    op.create_index(
        "ix_payouts_partner_status_created_at",
        "payouts",
        ["partner_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_payouts_partner_recipient_amount_created_at",
        "payouts",
        ["partner_id", "recipient", "amount", "created_at"],
        unique=False,
    )

    op.create_table(
        "payout_reservations",
        sa.Column("payout_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("partner_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("fee", sa.Numeric(18, 2), nullable=False),
        sa.Column("total", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payout_id"], ["payouts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_payout_reservations_partner_id", "payout_reservations", ["partner_id"], unique=False)
    op.create_index(
        "ix_payout_reservations_partner_status",
        "payout_reservations",
        ["partner_id", "status"],
        unique=False,
    )

    op.create_table(
        "payout_queue",
        sa.Column("payout_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("worker_id", sa.String(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["payout_id"], ["payouts.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_payout_queue_status_lease_created_at",
        "payout_queue",
        ["status", "lease_until", "created_at"],
        unique=False,
    )

    op.create_table(
        "payout_evidence",
        sa.Column("payout_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("executor_id", sa.String(), nullable=True),
        sa.Column("balance_before", sa.Numeric(18, 2), nullable=True),
        sa.Column("balance_after", sa.Numeric(18, 2), nullable=True),
        sa.Column("ussd_text", sa.Text(), nullable=True),
        sa.Column("provider_ref", sa.String(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["payout_id"], ["payouts.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("partner_name", sa.String(), nullable=True),
        sa.Column("partner_code", sa.String(), nullable=True),
        sa.Column("partner_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_users_id", "users", ["id"], unique=False)
    op.create_index("ix_users_partner_id", "users", ["partner_id"], unique=False)
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_partner_code", "users", ["partner_code"], unique=True)

    op.create_table(
        "balance_transactions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("partner_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("previous_balance", sa.Numeric(18, 2), nullable=False),
        sa.Column("new_balance", sa.Numeric(18, 2), nullable=False),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("admin_user", sa.Text(), nullable=True),
        sa.Column("adjustment_type", sa.Text(), nullable=True),
        sa.Column("balance_type", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("type IN ('deposit', 'withdrawal', 'adjustment', 'initial')", name="ck_balance_transactions_type"),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"]),
    )
    op.create_index("idx_balance_tx_partner", "balance_transactions", ["partner_id"], unique=False)
    op.create_index("idx_balance_tx_created", "balance_transactions", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_balance_tx_created", table_name="balance_transactions")
    op.drop_index("idx_balance_tx_partner", table_name="balance_transactions")
    op.drop_table("balance_transactions")

    op.drop_index("ix_users_partner_code", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_partner_id", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")

    op.drop_table("payout_evidence")

    op.drop_index("ix_payout_queue_status_lease_created_at", table_name="payout_queue")
    op.drop_table("payout_queue")

    op.drop_index("ix_payout_reservations_partner_status", table_name="payout_reservations")
    op.drop_index("ix_payout_reservations_partner_id", table_name="payout_reservations")
    op.drop_table("payout_reservations")

    op.drop_index("ix_payouts_partner_recipient_amount_created_at", table_name="payouts")
    op.drop_index("ix_payouts_partner_status_created_at", table_name="payouts")
    op.drop_index("ix_payouts_partner_id", table_name="payouts")
    op.drop_index("ix_payouts_created_at", table_name="payouts")
    op.drop_table("payouts")

    op.drop_index("ix_partners_api_key_prefix", table_name="partners")
    op.drop_table("partners")
