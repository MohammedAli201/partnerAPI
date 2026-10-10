"""Authenticated payout notifications, persisted with the payout change before delivery."""
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID, uuid4

from sqlalchemy import select

from models import PayoutWebhookEvent

logger = logging.getLogger(__name__)
WEBHOOK_STATUSES = {
    "PROCESSING": "Processing", "SENT": "Paid", "FAILED": "Failed",
    "REJECTED": "Rejected", "UNKNOWN":"Unknown", "CANCELLED":"Cancelled",
}


def payout_channel(payload):
    """Use the supplied delivery method verbatim; provider is not a channel."""
    for obj in (payload, payload.get("data", {})):
        if isinstance(obj, dict):
            for key in ("payout_channel", "deliveryMethod", "DeliveryMethod", "delivery_method"):
                value = obj.get(key)
                if isinstance(value, str) and value.strip():
                    return value
    raise ValueError("payout_channel (the backend delivery method) is required")


def callback_url(value):
    from webhook_transport import endpoint_url
    return endpoint_url(value)



def build_event(payout, final_status, event_time, default_url):
    status = WEBHOOK_STATUSES.get(final_status)
    if status is None:
        if final_status == "RECEIVED":
            return None
        raise ValueError("Unsupported payout status")
    payload = json.loads(payout.request_payload or "{}")
    # Stored references are either UUIDs or pm_<date>-<code>_<full UUID>.
    transaction_id = str(UUID(payout.partner_tx_id.rsplit("_", 1)[-1]))
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)
    event_time = event_time.astimezone(timezone.utc)
    event_id = uuid4()
    amount = Decimal(payout.amount)
    if not amount.is_finite() or amount <= 0:
        raise ValueError("Payout amount must be a positive finite decimal")
    body = {
        "event_id": str(event_id),
        "partner_tx_id": transaction_id,
        "status": status,
        "provider": payout.provider,
        # This is the stable payout id returned by /payouts-create and used for inquiry.
        "provider_reference": str(payout.id),
        "amount": amount,
        "currency": payout.currency,
        "recipient": payout.recipient,
        "payout_channel": payout_channel(payload),
        "timestamp": event_time.isoformat().replace("+00:00", "Z"),
    }
    # Emit Decimal as a JSON number without a lossy conversion through float.
    raw_body = ("{" + ",".join(
        json.dumps(key) + ":" + (format(value, "f") if isinstance(value, Decimal)
                                 else json.dumps(value, ensure_ascii=False, allow_nan=False))
        for key, value in body.items()
    ) + "}").encode("utf-8")
    return PayoutWebhookEvent(
        event_id=event_id, payout_id=payout.id,
        callback_url=callback_url(default_url) if default_url else "https://unregistered.invalid/blocked",
        raw_body=raw_body, attempts=0,
        created_at=event_time, next_attempt_at=datetime.now(timezone.utc),
    )


def enqueue_event(db,payout,final_status,event_time,default_url=None):
    from registered_webhooks import enqueue
    return enqueue(db,payout,final_status,event_time,default_url)



def signed_headers(secret, raw_body):
    if not secret or not secret.strip():
        raise ValueError("PAYOUT_STATUS_WEBHOOK_SECRET is required")
    timestamp = str(int(time.time()))
    nonce = str(uuid4())
    signature = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}.{nonce}.".encode("utf-8") + raw_body,
        hashlib.sha256,
    ).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-JubaTech-Timestamp": timestamp,
        "X-JubaTech-Nonce": nonce,
        "X-JubaTech-Signature": signature,
    }


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def authentication_headers(credential, raw_body, auth_mode):
    if auth_mode == "hmac":
        return signed_headers(credential, raw_body)
    if auth_mode == "api_key":
        if not credential or len(credential) < 32 or not credential.strip():
            raise ValueError("PAYOUT_STATUS_WEBHOOK_API_KEY must contain at least 32 characters")
        return {"Content-Type": "application/json", "X-API-Key": credential}
    raise ValueError("Unknown payout webhook authentication mode")


def deliver_event(event,credential,auth_mode="hmac"):
    raise RuntimeError("Unregistered/global callback delivery disabled; use registered_webhooks")



def deliver_next(session_factory,*unused):
    from registered_webhooks import deliver_next as deliver
    return deliver(session_factory)



def run_worker(stop,session_factory,*unused):
    from registered_webhooks import run_worker as worker
    return worker(stop,session_factory)

