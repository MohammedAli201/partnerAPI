"""Concurrency and crash-boundary checks for real SMS diagnostic dispatch."""
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
import backend_core as c
import sms_worker as sms
from test_phone_worker import connection
from test_existing_backend import pg, setup


@pytest.fixture
def batch(pg, connection, monkeypatch):
    monkeypatch.setenv('PHONE_SMS_TEST_ENABLED', 'true')
    body = dict(request_id=str(uuid4()), device_id=str(connection['data']['device']), recipient='97368681', count=10)
    client = connection['client']
    response = client.post('/admin/api/phone-workers/sms-batches', json=body)
    assert response.status_code == 200, response.text
    assert client.post('/admin/api/phone-workers/sms-batches', json=body).json() == response.json()
    assert client.post('/admin/api/phone-workers/sms-batches', json=dict(body, recipient='97368682')).status_code == 409
    return response.json()


def binding(job):
    return dict(job_id=job['job_id'], lease_id=job['lease_id'])


def test_ten_concurrent_claims_hold_one_job_until_completed(pg, connection, batch):
    device = connection['data']['device']
    def claim(_):
        with pg.begin() as db:
            return sms.claim(db, device)['job']
    with ThreadPoolExecutor(max_workers=10) as pool:
        jobs = list(pool.map(claim, range(10)))
    assert len({j['job_id'] for j in jobs}) == 1
    assert all(j['ordinal'] == 1 for j in jobs)
    client = connection['client']
    for n in range(1, 11):
        job = client.post('/v1/sms/claim').json()['job']
        assert job['ordinal'] == n and job['message'] == f'Message {n}'
        body = dict(**binding(job), subscription_id=1)
        assert client.post('/v1/sms/start', json=body).json()['can_send'] is True
        assert client.post('/v1/sms/start', json=body).json()['can_send'] is False
        assert client.post('/v1/sms/claim').json()['job'] is None
        result = dict(**binding(job), status='SENT', result_code=-1, detail='Android SMS sent callback: -1')
        assert client.post('/v1/sms/result', json=result).status_code == 200
        assert client.post('/v1/sms/result', json=result).status_code == 200
        assert client.post('/v1/sms/result', json=dict(result, status='FAILED', result_code=1)).status_code == 409
    assert client.post('/v1/sms/claim').json() == dict(job=None, blocked=None)
    with pg.begin() as db:
        assert c.row(db, "SELECT count(*) AS n FROM phone_sms_jobs WHERE status='SENT'")['n'] == 10
        assert c.row(db, 'SELECT count(*) AS n FROM payouts')['n'] == 0


def test_unknown_send_blocks_following_jobs_and_late_receipt_is_safe(pg, connection, batch):
    client = connection['client']
    job = client.post('/v1/sms/claim').json()['job']
    body = binding(job)
    assert client.post('/v1/sms/result', json=dict(body, status='SENT', result_code=-1, detail='premature')).status_code == 409
    assert client.post('/v1/sms/start', json=dict(body, subscription_id=1)).json()['can_send']
    with pg.begin() as db:
        c.run(db, "UPDATE phone_sms_jobs SET lease_until=now()-interval '1 second' WHERE id=:id", id=UUID(job['job_id']))
    assert client.post('/v1/sms/claim').json()['blocked']['status'] == 'UNKNOWN'
    assert client.post('/v1/sms/start', json=dict(body, subscription_id=1)).json()['can_send'] is False
    assert client.post('/v1/sms/result', json=dict(body, status='SENT', result_code=0, detail='not valid')).status_code == 409
    assert client.post('/v1/sms/result', json=dict(body, status='SENT', result_code=-1, detail='late Android sent callback')).status_code == 200
    assert client.post('/v1/sms/claim').json()['job']['ordinal'] == 2
    delivery = dict(body, delivery='DELIVERED')
    assert client.post('/v1/sms/delivery', json=delivery).status_code == 200
    assert client.post('/v1/sms/delivery', json=delivery).status_code == 200
    assert client.post('/v1/sms/delivery', json=dict(delivery, delivery='DELIVERY_FAILED')).status_code == 409


def test_expiry_before_send_moves_on_without_resending_and_checks_owner(pg, connection, batch):
    client = connection['client']
    job = client.post('/v1/sms/claim').json()['job']
    assert client.post('/v1/sms/start', json=dict(binding(job), lease_id=str(uuid4()), subscription_id=1)).status_code == 403
    with pg.begin() as db:
        c.run(db, "UPDATE phone_sms_jobs SET lease_until=now()-interval '1 second' WHERE id=:id", id=UUID(job['job_id']))
    next_job = client.post('/v1/sms/claim').json()['job']
    assert next_job['ordinal'] == 2
    assert client.post('/v1/sms/start', json=dict(**binding(job), subscription_id=1)).json()['can_send'] is False
