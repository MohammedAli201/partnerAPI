"""Payment POST automatically queues real SMS execution on the enrolled phone."""
from decimal import Decimal
from uuid import UUID, uuid4
import json
import pytest

import backend_core as c
from test_existing_backend import pg, setup, payload
from test_existing_http import client
from test_phone_worker import connection


def test_payment_creation_auto_sms_and_idle_worker_gets_next_payment(pg, setup, client, connection, monkeypatch):
    monkeypatch.setenv('PHONE_SMS_TEST_ENABLED', 'true')
    monkeypatch.setenv('SMS_PAYOUT_TEST_ENABLED', 'true')
    monkeypatch.setenv('SMS_PAYOUT_TEST_RECIPIENT', '97368681')
    http, main = client
    partner_headers = {'X-API-Key': setup['key']}
    phone_headers = {'Authorization': 'Bearer ' + connection['credentials']['access_token']}
    # A worker already waiting with an empty queue gets the new payment automatically.
    assert http.post('/v1/sms/claim', headers=phone_headers, json={'worker_version':2}).json()['job'] is None
    first = payload(reference=str(uuid4()), provider='EVC', recipient='97368681', payout_channel=None,
                    request_payload={'beneficiary': {'mobile': '+252615738865', 'network': 'Hormuud'}}).model_dump(mode='json')
    headers = dict(partner_headers, **{'Idempotency-Key': first['partner_tx_id']})
    created = http.post('/payouts-create', headers=headers, json=first)
    assert created.status_code == 201, created.text
    accepted = created.json()
    assert accepted['execution']['mode'] == 'SMS_TEST'
    assert accepted['execution']['sms_status'] == 'QUEUED'
    assert accepted['execution']['payment_executed'] is False
    with pg.begin() as db:
        stored = c.row(db, 'SELECT provider,recipient FROM payouts WHERE id=:id', id=UUID(accepted['id']))
        assert stored['provider'] == 'EVC' and stored['recipient'] == '97368681'
    assert http.post('/payouts-create', headers=headers, json=first).json() == accepted
    assert http.post('/v1/sms/claim', headers=phone_headers).json()['job'] is None
    job = http.post('/v1/sms/claim', headers=phone_headers, json={'worker_version':2}).json()['job']
    assert job['payout_id'] == accepted['id'] and job['kind'] == 'SMS_PAYOUT_TEST'
    assert job['recipient'] == '97368681' and '10.00 USD' in job['message']
    with pg.begin() as db:
        assert c.row(db, 'SELECT count(*) AS n FROM phone_sms_jobs')['n'] == 1
        assert c.row(db, 'SELECT status FROM payout_queue WHERE payout_id=:id', id=UUID(accepted['id']))['status'] == 'HELD'
        assert c.row(db, 'SELECT count(*) AS n FROM payout_attempts')['n'] == 0
    second_payload = payload(reference=str(uuid4())).model_dump(mode='json')
    second = http.post('/payouts-create', headers=partner_headers, json=second_payload).json()
    assert http.post('/v1/sms/claim', headers=phone_headers, json={'worker_version':2}).json()['job']['job_id'] == job['job_id']
    binding = dict(job_id=job['job_id'], lease_id=job['lease_id'])
    assert http.post('/v1/sms/start', headers=phone_headers, json=dict(binding, subscription_id=17)).json()['can_send']
    result = dict(binding, status='SENT', result_code=-1, detail='Android SMS sent callback: -1')
    assert http.post('/v1/sms/result', headers=phone_headers, json=result).status_code == 200
    assert http.post('/v1/sms/result', headers=phone_headers, json=result).status_code == 200
    fetched = http.get('/payouts/' + accepted['id'], headers=partner_headers).json()
    assert fetched['execution']['sms_status'] == 'SENT'
    assert fetched['status'] == 'CANCELLED' and fetched['reservation']['status'] == 'RELEASED'
    assert fetched['execution']['payment_executed'] is False
    assert http.post('/v1/sms/claim', headers=phone_headers, json={'worker_version':2}).json()['job']['payout_id'] == second['id']
    with pg.begin() as db:
        assert c.row(db, "SELECT count(*) AS n FROM ledger_journals WHERE event_type='PAYOUT'")['n'] == 0
        assert c.row(db, 'SELECT balance_available FROM partners WHERE id=:id', id=setup['partner'])['balance_available'] == Decimal('989.40')
        # Only the second, still queued SMS test holds a reservation; no funds were spent.
        assert c.row(db, 'SELECT balance_reserved FROM partners WHERE id=:id', id=setup['partner'])['balance_reserved'] == Decimal('10.60')


def test_no_matching_phone_rolls_back_payment_and_reservation(pg, setup, client, connection, monkeypatch):
    monkeypatch.setenv('PHONE_SMS_TEST_ENABLED', 'true')
    monkeypatch.setenv('SMS_PAYOUT_TEST_ENABLED', 'true')
    http, main = client
    response = http.post('/payouts-create', headers={'X-API-Key': setup['key']},
                         json=payload(provider='Zaad').model_dump(mode='json'))
    assert response.status_code == 503, response.text
    with pg.begin() as db:
        assert c.row(db, 'SELECT count(*) AS n FROM payouts')['n'] == 0
        assert c.row(db, 'SELECT balance_reserved FROM partners WHERE id=:id', id=setup['partner'])['balance_reserved'] == 0


def test_sms_substitute_is_rejected_in_production(pg, setup, client, connection, monkeypatch):
    monkeypatch.setenv('PHONE_SMS_TEST_ENABLED', 'true')
    monkeypatch.setenv('SMS_PAYOUT_TEST_ENABLED', 'true')
    monkeypatch.setenv('ENVIRONMENT', 'production')
    http, main = client
    response = http.post('/payouts-create', headers={'X-API-Key': setup['key']}, json=payload().model_dump(mode='json'))
    assert response.status_code == 503, response.text
    with pg.begin() as db:
        assert c.row(db, 'SELECT count(*) AS n FROM payouts')['n'] == 0


@pytest.mark.parametrize('outcome,uncertain_first', [('SENT', False), ('SENT', True), ('FAILED', False)])
def test_sms_accounting_follows_result_exactly_once(pg, setup, client, connection, monkeypatch, outcome, uncertain_first):
    monkeypatch.setenv('PHONE_SMS_TEST_ENABLED', 'true')
    monkeypatch.setenv('SMS_PAYOUT_TEST_ENABLED', 'true')
    monkeypatch.setenv('SMS_PAYOUT_TEST_ACCOUNTING', 'true')
    monkeypatch.setenv('SMS_PAYOUT_TEST_RECIPIENT', '97368681')
    http, _ = client
    headers = {'X-API-Key': setup['key']}
    phone = {'Authorization': 'Bearer ' + connection['credentials']['access_token']}
    body = payload(amount='50.00', provider='EVC', recipient='97368681', payout_channel=None,
                   request_payload={'callback_url':'https://partner.example.com/webhooks/payout-status'}).model_dump(mode='json')
    monkeypatch.setenv('ENVIRONMENT', 'development')
    response = http.post('/payouts-create', headers=headers, json=body)
    assert response.status_code == 201, response.text
    payment = response.json()['id']
    job = http.post('/v1/sms/claim', headers=phone, json={'worker_version': 2}).json()['job']
    binding = dict(job_id=job['job_id'], lease_id=job['lease_id'])
    assert http.post('/v1/sms/start', headers=phone, json=dict(binding, subscription_id=17)).status_code == 200
    code = -1 if outcome == 'SENT' else 1
    result = dict(binding, status=outcome, result_code=code, detail=f'Android SMS sent callback: {code}')
    if uncertain_first:
        pending = dict(binding, status='UNKNOWN', detail='Callback pending')
        assert http.post('/v1/sms/result', headers=phone, json=pending).status_code == 200
        with pg.begin() as db:
            assert c.row(db, 'SELECT balance_reserved FROM partners WHERE id=:id', id=setup['partner'])['balance_reserved'] == Decimal('50.60')
            assert c.row(db, 'SELECT count(*) n FROM fee_financial_events WHERE payout_id=:id', id=UUID(payment))['n'] == 0
    for _ in range(2):
        assert http.post('/v1/sms/result', headers=phone, json=result).status_code == 200
    fetched = http.get('/payouts/' + payment, headers=headers).json()
    assert fetched['status'] == outcome
    assert fetched['reservation']['status'] == ('CAPTURED' if outcome == 'SENT' else 'RELEASED')
    assert fetched['execution']['payment_executed'] is False
    with pg.begin() as db:
        partner = c.row(db, 'SELECT balance_available,balance_reserved FROM partners WHERE id=:id', id=setup['partner'])
        assert partner['balance_available'] == (Decimal('949.40') if outcome == 'SENT' else Decimal('1000.00'))
        assert partner['balance_reserved'] == 0
        fee = c.row(db, 'SELECT amount_minor,activity FROM fee_financial_events WHERE payout_id=:id', id=UUID(payment))
        if outcome == 'SENT':
            assert fee['amount_minor'] == 60 and fee['activity'] == 'simulation'
        else:
            assert fee is None
        assert c.row(db, "SELECT count(*) n FROM ledger_journals WHERE payout_id=:id AND event_type='PAYOUT'", id=UUID(payment))['n'] == (1 if outcome == 'SENT' else 0)
        event = c.row(db, 'SELECT raw_body,state,endpoint_id FROM payout_webhook_events WHERE payout_id=:id ORDER BY status_version DESC LIMIT 1', id=UUID(payment))
        assert json.loads(bytes(event['raw_body']))['execution_mode'] == 'SMS_TEST'
        assert event['state'] == 'BLOCKED' and event['endpoint_id'] is None
