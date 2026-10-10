from decimal import Decimal
from typing import Any, Dict, Literal
from uuid import UUID

from pydantic import BaseModel, Field,field_validator

PayoutBusinessStatus = Literal["RECEIVED", "PROCESSING", "SENT", "FAILED", "REJECTED", "UNKNOWN", "CANCELLED"]
QueueStatus = Literal["PENDING", "IN_PROGRESS"]


class PayoutCreate(BaseModel):
    partner_tx_id: str = Field(..., min_length=1, max_length=128)
    amount: Decimal = Field(..., gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=8)
    recipient: str = Field(..., min_length=3, max_length=64)
    provider: str = Field(..., min_length=2, max_length=64)
    payout_channel: str | None = Field(default=None, min_length=1, max_length=64)
    request_payload: Dict[str, Any]

    @field_validator('currency')
    @classmethod
    def supported_currency(cls,value):
        value=value.strip().upper()
        if value not in ('USD','EUR','GBP'):
            raise ValueError('Supported currencies USD/EUR/GBP use scale 2')
        return value


class PayoutStatusUpdate(BaseModel):
    status: PayoutBusinessStatus


class ExecutorClaimRequest(BaseModel):
    executor_id: str = Field(..., min_length=2, max_length=64)
    batch_size: int = Field(default=10, ge=1, le=100)
    lease_secs: int = Field(default=120, ge=30, le=900)


class ExecutorReport(BaseModel):
    payout_id: UUID
    executor_id: str = Field(..., min_length=2, max_length=64)
    balance_before: Decimal | None = None
    balance_after: Decimal | None = None
    ussd_text: str | None = ""
    provider_ref: str | None = None
