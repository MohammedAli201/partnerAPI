import uuid
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    BigInteger,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class PublicPartnershipEnquiry(Base):
    __tablename__ = 'public_partnership_enquiries'
    __table_args__ = (Index('ix_public_partnership_enquiries_created','created_at','id'),)
    id = Column(UUID(as_uuid=True),primary_key=True)
    reference = Column(String(32),nullable=False,unique=True)
    payload_hash = Column(String(64),nullable=False)
    company_name = Column(String(160),nullable=False)
    country = Column(String(100),nullable=False)
    contact_name = Column(String(100),nullable=False)
    email = Column(String(254),nullable=False)
    monthly_volume = Column(String(64),nullable=False)
    channels = Column(String(64),nullable=False)
    created_at = Column(DateTime(timezone=True),nullable=False,server_default=text('now()'))


class Partner(Base):
    __tablename__ = "partners"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    api_key_prefix = Column(String(8), nullable=False, unique=True, index=True)
    api_key_hash = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True, server_default=text("true"), nullable=False)
    balance_available = Column(Numeric(18, 2), default=0, server_default=text("0"), nullable=False)
    balance_reserved = Column(Numeric(18, 2), default=0, server_default=text("0"), nullable=False)
    funding_currency = Column(String(3), nullable=False, server_default=text("'USD'"))
    ledger_enabled = Column(Boolean, nullable=False, server_default=text("false"))
    paused = Column(Boolean, nullable=False, server_default=text("false"))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=text("now()"), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, server_default=text("now()"), nullable=False)


class Payout(Base):
    __tablename__ = "payouts"
    __table_args__ = (
        UniqueConstraint("partner_id", "partner_tx_id", name="uq_payouts_partner_partner_tx_id"),
        Index("ix_payouts_partner_status_created_at", "partner_id", "status", "created_at"),
        Index("ix_payouts_partner_recipient_amount_created_at", "partner_id", "recipient", "amount", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    partner_id = Column(Integer, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False, index=True)
    partner_tx_id = Column(String, nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(8), nullable=False, default="USD", server_default=text("'USD'"))
    recipient = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    status = Column(String, nullable=False, default="RECEIVED", server_default=text("'RECEIVED'"))
    request_payload = Column(Text, nullable=True)
    canonical_hash = Column(String(64))
    status_version = Column(Integer, nullable=False, default=1, server_default=text('1'))
    hold_reason = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default=text("now()"), index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default=text("now()"))

    partner = relationship("Partner")


class PayoutWebhookEvent(Base):
    __tablename__ = "payout_webhook_events"
    __table_args__ = (
        Index("ix_payout_webhook_events_due", "accepted_at", "next_attempt_at"),
    )

    event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payout_id = Column(UUID(as_uuid=True), ForeignKey("payouts.id", ondelete="RESTRICT"), nullable=False)
    callback_url = Column(Text, nullable=False)
    raw_body = Column(LargeBinary, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    last_status_code = Column(Integer, nullable=True)
    last_error = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    partner_id = Column(Integer, ForeignKey('partners.id'))
    endpoint_id = Column(UUID(as_uuid=True))
    state = Column(String, nullable=False, default='BLOCKED', server_default=text("'BLOCKED'"))
    lease_until = Column(DateTime(timezone=True))
    lease_owner = Column(UUID(as_uuid=True))
    generation = Column(BigInteger, nullable=False, default=0, server_default=text('0'))
    status_version = Column(Integer)


class PayoutReservation(Base):
    __tablename__ = "payout_reservations"
    __table_args__ = (
        Index("ix_payout_reservations_partner_status", "partner_id", "status"),
    )

    payout_id = Column(UUID(as_uuid=True), ForeignKey("payouts.id", ondelete="CASCADE"), primary_key=True)
    partner_id = Column(Integer, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount = Column(Numeric(18, 2), nullable=False)
    fee = Column(Numeric(18, 2), nullable=False)
    total = Column(Numeric(18, 2), nullable=False)
    status = Column(String, nullable=False, default="ACTIVE", server_default=text("'ACTIVE'"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default=text("now()"))

    partner = relationship("Partner")
    payout = relationship("Payout")


class PayoutQueue(Base):
    __tablename__ = "payout_queue"
    __table_args__ = (
        Index("ix_payout_queue_status_lease_created_at", "status", "lease_until", "created_at"),
    )

    payout_id = Column(UUID(as_uuid=True), ForeignKey("payouts.id", ondelete="CASCADE"), primary_key=True)
    status = Column(String, nullable=False, default="PENDING", server_default=text("'PENDING'"))
    worker_id = Column(String, nullable=True)
    lease_until = Column(DateTime(timezone=True), nullable=True)
    generation = Column(BigInteger, nullable=False, default=0, server_default=text('0'))
    dispatch_count = Column(Integer, nullable=False, default=0, server_default=text('0'))
    available_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default=text("now()"))


class PayoutEvidence(Base):
    __tablename__ = "payout_evidence"

    payout_id = Column(UUID(as_uuid=True), ForeignKey("payouts.id", ondelete="CASCADE"), primary_key=True)
    executor_id = Column(String, nullable=True)
    balance_before = Column(Numeric(18, 2), nullable=True)
    balance_after = Column(Numeric(18, 2), nullable=True)
    ussd_text = Column(Text, nullable=True)
    provider_ref = Column(String, nullable=True)
    captured_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, server_default=text("now()"))


class PartnerSignup(BaseModel):
    partner_name: str
    username: str
    password: str


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, server_default=text("true"), nullable=False)
    partner_name = Column(String, nullable=True)
    partner_code = Column(String, unique=True, nullable=True)
    partner_id = Column(Integer, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=True, index=True)

    partner = relationship("Partner")
