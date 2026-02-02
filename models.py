# models.py
import uuid
from sqlalchemy import (
    Column, String, Boolean, Numeric, ForeignKey, Text, UniqueConstraint,
    Integer
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from database import Base


class Partner(Base):
    __tablename__ = "partners"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    api_key_hash = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class Payout(Base):
    __tablename__ = "payouts"
    __table_args__ = (
        UniqueConstraint("partner_id", "partner_tx_id", name="uq_partner_partner_tx_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    partner_id = Column(UUID(as_uuid=True), ForeignKey("partners.id"), nullable=False)
    partner_tx_id = Column(Text, nullable=False)

    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(Text, nullable=False, server_default="USD")
    recipient = Column(Text, nullable=False)
    provider = Column(Text, nullable=False)

    # This is business status (truth). Example values:
    # RECEIVED -> PROCESSING -> SENT/FAILED
    status = Column(Text, nullable=False, server_default="RECEIVED")

    request_payload = Column(JSONB, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # Optional relationship (one-to-one) to queue row
    queue = relationship("PayoutQueue", back_populates="payout", uselist=False, cascade="all, delete")


class PayoutQueue(Base):
    __tablename__ = "payout_queue"

    # payout_id is primary key + FK -> payouts.id, and will be deleted if payout is deleted
    payout_id = Column(UUID(as_uuid=True), ForeignKey("payouts.id", ondelete="CASCADE"), primary_key=True)

    # Queue status is operational (worker state)
    # PENDING | IN_PROGRESS
    status = Column(Text, nullable=False, server_default="PENDING")

    worker_id = Column(Text, nullable=True)
    lease_until = Column(TIMESTAMP(timezone=True), nullable=True)

    retry_count = Column(Integer, nullable=False, server_default="0")
    max_retries = Column(Integer, nullable=False, server_default="5")

    last_error = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    payout = relationship("Payout", back_populates="queue")

class PayoutEvidence(Base):
    __tablename__ = "payout_evidence"

    payout_id = Column(
        UUID(as_uuid=True),
        ForeignKey("payouts.id", ondelete="CASCADE"),
        primary_key=True
    )

    executor_id = Column(Text, nullable=False)

    balance_before = Column(Numeric(18, 2), nullable=True)
    balance_after  = Column(Numeric(18, 2), nullable=True)

    ussd_text = Column(Text, nullable=True)
    provider_ref = Column(Text, nullable=True)

    captured_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now()
    )
class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    payout_id = Column(
        UUID(as_uuid=True),
        ForeignKey("payouts.id", ondelete="CASCADE"),
        nullable=False
    )

    partner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("partners.id"),
        nullable=False
    )

    event_type = Column(Text, nullable=False)  # payout.status_changed
    payload = Column(JSONB, nullable=False)

    status = Column(Text, nullable=False, server_default="PENDING")  # PENDING|SENT|FAILED
    attempts = Column(Integer, nullable=False, server_default="0")

    last_error = Column(Text, nullable=True)
    next_retry_at = Column(TIMESTAMP(timezone=True), nullable=True)

    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now()
    )

    sent_at = Column(TIMESTAMP(timezone=True), nullable=True)
