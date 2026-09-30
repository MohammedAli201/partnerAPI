from typing import Dict, Any
import json
from pydantic import BaseModel, Field
from typing import Optional, Any, Literal
from uuid import UUID
from decimal import Decimal

# ---- Business statuses ----
PayoutBusinessStatus = Literal["RECEIVED", "PROCESSING", "SENT", "FAILED"]

# ---- Queue statuses ----
QueueStatus = Literal["PENDING", "IN_PROGRESS"]
class PayoutCreate(BaseModel):
    partner_tx_id: str
    amount: float
    currency: str = "USD"
    recipient: str
    provider: str
    request_payload: Dict[str, Any]  # ✅ Accept dict, not string
    
    class Config:
        arbitrary_types_allowed = True
# class PayoutCreate(BaseModel):
#     partner_tx_id: str = Field(..., min_length=3, max_length=128)
#     amount: Decimal = Field(..., gt=0)
#     currency: str = Field(default="USD", min_length=3, max_length=8)
#     recipient: str = Field(..., min_length=3, max_length=64)
#     provider: str = Field(..., min_length=2, max_length=64)
#     request_payload: Optional[str] = None

class PayoutStatusUpdate(BaseModel):
    status: PayoutBusinessStatus

class ExecutorClaimRequest(BaseModel):
    executor_id: str = Field(..., min_length=2, max_length=64)
    batch_size: int = Field(default=10, ge=1, le=100)
    lease_secs: int = Field(default=120, ge=30, le=900)

class ExecutorReport(BaseModel):
    payout_id: UUID
    executor_id: str = Field(..., min_length=2, max_length=64)

    balance_before: Optional[Decimal] = None
    balance_after: Optional[Decimal] = None
    ussd_text: Optional[str] = ""
    provider_ref: Optional[str] = None
