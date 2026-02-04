

# models.py
import uuid
from pydantic import BaseModel

from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Boolean,
    DateTime, Numeric, ForeignKey, Text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# class Partner(Base):
#     __tablename__ = "partners"

#     id = Column(Integer, primary_key=True)
#     name = Column(String, nullable=False)

#     api_key_prefix = Column(String(8), nullable=False, index=True)
#     api_key_hash = Column(String(200), nullable=False)

#     is_active = Column(Boolean, default=True, nullable=False)

#     created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
class Partner(Base):
    __tablename__ = "partners"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)

    api_key_prefix = Column(String(8), nullable=False, index=True)
    api_key_hash = Column(String(200), nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)

    # optional cached balances (recommended)
    balance_available = Column(Numeric(18, 2), nullable=False, default=0)
    balance_reserved = Column(Numeric(18, 2), nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
class PayoutReservation(Base):
    __tablename__ = "payout_reservations"

    payout_id = Column(UUID(as_uuid=True), ForeignKey("payouts.id", ondelete="CASCADE"), primary_key=True)
    partner_id = Column(Integer, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False, index=True)

    amount = Column(Numeric(18, 2), nullable=False)  # principal
    fee = Column(Numeric(18, 2), nullable=False)
    total = Column(Numeric(18, 2), nullable=False)

    status = Column(String, nullable=False, default="ACTIVE")  # ACTIVE, RELEASED, CAPTURED
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    partner = relationship("Partner")
    payout = relationship("Payout")

class Payout(Base):
    __tablename__ = "payouts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    partner_id = Column(Integer, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False)
    partner_tx_id = Column(String, nullable=False)

    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(8), nullable=False, default="USD")
    recipient = Column(String, nullable=False)
    provider = Column(String, nullable=False)

    # Business status (strict)
    # RECEIVED -> PROCESSING -> SENT/FAILED
    status = Column(String, nullable=False, default="RECEIVED")

    request_payload = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    partner = relationship("Partner")

class PayoutQueue(Base):
    __tablename__ = "payout_queue"

    payout_id = Column(UUID(as_uuid=True), ForeignKey("payouts.id", ondelete="CASCADE"), primary_key=True)

    # Technical queue status
    # PENDING -> IN_PROGRESS -> (deleted when finalized)
    status = Column(String, nullable=False, default="PENDING")

    worker_id = Column(String, nullable=True)         # executor_id that claimed
    lease_until = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class PayoutEvidence(Base):
    __tablename__ = "payout_evidence"

    payout_id = Column(UUID(as_uuid=True), ForeignKey("payouts.id", ondelete="CASCADE"), primary_key=True)

    executor_id = Column(String, nullable=True)

    balance_before = Column(Numeric(18, 2), nullable=True)
    balance_after = Column(Numeric(18, 2), nullable=True)

    ussd_text = Column(Text, nullable=True)
    provider_ref = Column(String, nullable=True)

    captured_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
class PartnerSignup(BaseModel):
    partner_name: str
    username: str
    password: str
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    # login
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)

    # authorization
    role = Column(String, nullable=False)  # "admin" | "partner"
    is_active = Column(Boolean, default=True, nullable=False)

    # partner info (only when role="partner")
    partner_name = Column(String, nullable=True)
    partner_code = Column(String, unique=True, nullable=True)

    partner_id = Column(Integer, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=True)
    partner = relationship("Partner")


    id = Column(Integer, primary_key=True, index=True)

    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)

    role = Column(String, nullable=False)  # "admin" | "partner"
    is_active = Column(Boolean, default=True)

    partner_name = Column(String, nullable=True)
    partner_code = Column(String, unique=True, nullable=True)

    # ✅ ADD THESE TWO LINES:
    partner_id = Column(Integer, ForeignKey("partners.id", ondelete="RESTRICT"), nullable=True)
    partner = relationship("Partner")
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    # login
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)

    # authorization
    role = Column(String, nullable=False)  # "admin" | "partner"
    is_active = Column(Boolean, default=True)

    # partner info (ONLY used when role="partner")
    partner_name = Column(String, nullable=True)   # e.g. "Partner Ltd"
    partner_code = Column(String, unique=True, nullable=True) 