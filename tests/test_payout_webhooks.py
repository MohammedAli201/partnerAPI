import hashlib


import hmac


import json


from datetime import datetime, timedelta, timezone


from decimal import Decimal


from types import SimpleNamespace


from urllib.error import HTTPError, URLError


from uuid import UUID, uuid4


import pytest


from pydantic import ValidationError


from sqlalchemy import create_engine, select


from sqlalchemy.orm import sessionmaker


import payout_webhooks as webhooks


from models import PayoutWebhookEvent


from schemas import PayoutCreate


from test_hardening import load_main_module, make_request, endpoint_fn


def payout(**overrides):
    values = dict(
        id=uuid4(), partner_tx_id=f"pm_260915-ABC123_{uuid4()}",
        amount=Decimal("9999999999999999.99"), currency="USD", provider="Hormuud",
        recipient="+252611234567",
        request_payload=json.dumps({"DeliveryMethod": "evc"}),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def event(status="SENT", **overrides):
    return webhooks.build_event(payout(**overrides), status,
                               datetime(2026, 9, 15, 12, tzinfo=timezone.utc),
                               "https://registered.example/api/webhooks/payout-status")


@pytest.mark.parametrize("local,expected", [
    ("SENT", "Paid"), ("PROCESSING", "Processing"), ("FAILED", "Failed"), ("REJECTED", "Rejected"),
])
def test_complete_event_contract_and_exact_numeric_amount(local, expected):
    source = payout()
    result = webhooks.build_event(source, local, datetime(2026, 9, 15, 12), "https://backend.example/callback")
    body = json.loads(result.raw_body, parse_float=Decimal)
    UUID(body["event_id"])
    assert body == {
        "event_id": str(result.event_id), "partner_tx_id": source.partner_tx_id.rsplit("_", 1)[-1],
        "status": expected, "provider": "Hormuud", "provider_reference": str(source.id),
        "amount": Decimal("9999999999999999.99"), "currency": "USD",
        "recipient": source.recipient, "payout_channel": "evc", "timestamp": "2026-09-15T12:00:00Z",
    }
    assert b'"amount":9999999999999999.99' in result.raw_body


def test_reference_is_stable_between_status_changes():
    source = payout()
    bodies = [json.loads(webhooks.build_event(source, status, datetime.now(timezone.utc),
                                             "https://backend.example/callback").raw_body)
              for status in ("PROCESSING", "SENT")]
    assert bodies[0]["event_id"] != bodies[1]["event_id"]
    assert bodies[0]["provider_reference"] == bodies[1]["provider_reference"] == str(source.id)


def test_does_not_invent_a_missing_delivery_method():
    with pytest.raises(ValueError, match="payout_channel"):
        event(request_payload="{}")


def test_hmac_covers_actual_utf8_body_and_new_headers_each_time(monkeypatch):
    raw = event(provider="Hormuud-é").raw_body
    monkeypatch.setattr(webhooks.time, "time", lambda: 1800012345)
    first = webhooks.signed_headers("test-secret-é", raw)
    second = webhooks.signed_headers("test-secret-é", raw)
    for headers in (first, second):
        UUID(headers["X-JubaTech-Nonce"])
        assert headers["Content-Type"] == "application/json"
        assert headers["X-JubaTech-Timestamp"] == "1800012345"
        signed = (headers["X-JubaTech-Timestamp"] + "." + headers["X-JubaTech-Nonce"] + ".").encode() + raw
        assert headers["X-JubaTech-Signature"] == hmac.new("test-secret-é".encode(), signed, hashlib.sha256).hexdigest()
        assert headers["X-JubaTech-Signature"] != hmac.new("test-secret-é".encode(), signed + b" ", hashlib.sha256).hexdigest()
    assert first["X-JubaTech-Nonce"] != second["X-JubaTech-Nonce"]
    assert first["X-JubaTech-Signature"] != second["X-JubaTech-Signature"]


def test_create_requires_channel_before_reserving_funds(monkeypatch):
    main = load_main_module(monkeypatch)
    body = main.PayoutCreate(partner_tx_id=str(uuid4()), amount=Decimal("10.00"),
                             recipient="+252611234567", provider="Hormuud", request_payload={})
    with pytest.raises(main.HTTPException) as error:
        import backend_core
        backend_core.admission(None,1,body,body.partner_tx_id,None,Decimal('.60'))
    assert error.value.status_code == 422


def test_create_does_not_silently_round_amount_in_database():
    with pytest.raises(ValidationError):
        PayoutCreate(partner_tx_id=str(uuid4()), amount=Decimal("10.005"),
                     recipient="+252611234567", provider="Hormuud",
                     payout_channel="evc", request_payload={})


def test_per_payout_destination_is_ignored_by_renderer():
    result=event(request_payload=json.dumps({'payout_channel':'evc','callback_url':'https://evil.example/steal'}))
    assert result.callback_url=='https://registered.example/api/webhooks/payout-status'


def test_global_credential_delivery_permanently_disabled():
    with pytest.raises(RuntimeError,match='disabled'):
        webhooks.deliver_event(event(),'global-secret')
