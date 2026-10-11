"""Actual Android wire contract against a disposable Hubaal PostgreSQL database."""
import base64
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import backend_core as c
import payment_worker as w
import phone_worker as phone
from test_existing_backend import pg, setup, payload, submit


def proof(key, message):
    return base64.b64encode(key.sign(message.encode(), ec.ECDSA(hashes.SHA256()))).decode()


@pytest.fixture
def connection(pg, setup, monkeypatch):
    monkeypatch.setenv('ENVIRONMENT', 'test')
    monkeypatch.setenv('PHONE_WORKER_ENABLED', 'true')
    monkeypatch.setenv('PHONE_WORKER_SIMULATOR_SETTLEMENT', 'true')
    sessions = sessionmaker(pg)
    def get_db():
        with sessions() as db:
            yield db
    def role(_):
        return lambda: dict(uid=setup['admins'][0]['id'])
    app = FastAPI()
    app.include_router(phone.make_router(get_db, role))
    client = TestClient(app)
    key = ec.generate_private_key(ec.SECP256R1())
    pub = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
    with pg.begin() as db:
        code = phone.enrollment_code(db, setup['device'], 'test')['code']
    body = dict(code=code, public_key=pub, signature=proof(key, 'enroll:' + code))
    response = client.post('/v1/enroll', json=body)
    assert response.status_code == 200, response.text
    credentials = response.json()
    client.headers['Authorization'] = 'Bearer ' + credentials['access_token']
    yield dict(client=client, key=key, credentials=credentials, enrollment=body, data=setup)
    client.close()



def test_enrollment_one_use_proof_rotation_revocation_and_environment(pg, connection, monkeypatch):
    client, key = connection['client'], connection['key']
    assert client.post('/v1/enroll', json=connection['enrollment']).status_code == 401
    renew = dict(device_id=str(connection['data']['device']), refresh_token=connection['credentials']['refresh_token'], signature='bad')
    assert client.post('/v1/renew', json=renew).status_code == 401
    renew['signature'] = proof(key, 'renew:' + renew['refresh_token'])
    response = client.post('/v1/renew', json=renew)
    assert response.status_code == 200
    assert client.post('/v1/renew', json=renew).status_code == 401
    assert client.post('/v1/claim', json=dict(wait_seconds=1)).status_code == 401
    client.headers['Authorization'] = 'Bearer ' + response.json()['access_token']
    assert client.post('/v1/claim', json=dict(wait_seconds=1)).status_code == 503
    assert client.post('/v1/authorize', json=dict(attempt_id=str(uuid4()), payload_hash='a' * 64,
                                               assignment_version=1)).status_code == 503
    monkeypatch.setenv('ENVIRONMENT', 'production')
    assert client.post('/v1/claim', json=dict(wait_seconds=1)).status_code == 503
    monkeypatch.setenv('ENVIRONMENT', 'test')
    with pg.begin() as db:
        phone.device_control(db, connection['data']['device'], 'revoke', 'test')
    assert client.post('/v1/claim', json=dict(wait_seconds=1)).status_code == 401



def test_real_sim_instruction_without_any_payout(pg, connection, monkeypatch):
    monkeypatch.setenv('PHONE_USSD_TEST_ENABLED', 'true')
    monkeypatch.setenv('PHONE_WORKER_SIMULATOR_SETTLEMENT', 'false')
    client = connection['client']
    with pg.begin() as db:
        c.run(db, 'UPDATE payment_workers SET enabled=false,simulator=false WHERE id=:id',
              id=connection['data']['worker']['id'])
    body = dict(request_id=str(uuid4()), recipient='615738865')
    response = client.post('/v1/ussd-tests/standalone', json=body)
    assert response.status_code == 200, response.text
    test = response.json()
    assert test['command'] == '*125*615738865#'
    assert client.post('/v1/ussd-tests/standalone', json=body).json() == test
    assert client.post('/v1/ussd-tests/standalone', json=dict(body, recipient='611234567')).status_code == 409
    assert client.post('/v1/ussd-tests/standalone', json=dict(body, recipient='615738865#')).status_code == 422
    result = dict(test_id=test['test_id'], status='REQUESTED')
    assert client.post('/v1/ussd-tests/result', json=result).status_code == 200
    result.update(status='FAILED', response='Carrier/Android failure code: -1')
    assert client.post('/v1/ussd-tests/result', json=result).status_code == 200
    assert client.post('/v1/ussd-tests/result', json=result).status_code == 200
    assert client.post('/v1/ussd-tests/standalone', json=body).json()['status'] == 'FAILED'
    assert client.get('/admin/api/phone-workers/ussd-tests').json()[0]['payout_id'] is None
    with pg.begin() as db:
        assert c.row(db, 'SELECT count(*) AS n FROM payouts')['n'] == 0
        assert c.row(db, "SELECT count(*) AS n FROM ledger_journals WHERE event_type='PAYOUT'")['n'] == 0
