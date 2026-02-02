# schemas.py
from pydantic import BaseModel, Field, condecimal
from typing import Any, Dict
from enum import Enum

class PayoutCreate(BaseModel):
    partner_tx_id: str = Field(..., min_length=1)
    amount: condecimal(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    recipient: str
    provider: str
    request_payload: Dict[str, Any]
class PayoutStatus(str, Enum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    FAILED = "FAILED"

class PayoutStatusUpdate(BaseModel):
    status: PayoutStatus


# schemas.py
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from decimal import Decimal

class ExecutorReport(BaseModel):
    payout_id: UUID
    executor_id: str = Field(..., min_length=1)

    balance_before: Optional[Decimal] = None
    balance_after: Optional[Decimal] = None

    ussd_text: str = Field(default="")
    provider_ref: Optional[str] = None
class ExecutorClaimRequest(BaseModel):
    executor_id: str = Field(..., min_length=1)
    batch_size: int = Field(default=10, gt=0, le=100)
    lease_secs: int = Field(default=120, gt=0, le=3600)