from fastapi import APIRouter, Request
from datetime import datetime, timezone

router = APIRouter()


@router.post("/api/webhooks/payout-status")
def payout_status_webhook(request: Request):
    """Simple webhook endpoint that returns a standard payout-status payload.

    This mirrors existing router naming conventions (routes_*.py).
    """
    # In a real integration you would parse and validate the incoming
    # request body, verify signatures, and update DB state. Here we
    # return the example response structure requested.
    return {
        "partner_tx_id": "<transaction-guid-or-partner-reference>",
        "status": "paid",
        "payout_id": "provider-payout-id",
        "provider_reference": "provider-reference",
        "amount": "100.00",
        "currency": "USD",
        "recipient": "+252...",
        "provider": "EVC",
        "completed_at": datetime.now(timezone.utc).isoformat()
    }
