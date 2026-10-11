"""One active real SMS diagnostic per phone; no replay after the send boundary."""
import os
from datetime import datetime, timezone, timedelta
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field
import backend_core as c
from sms_payout import complete_payment_test


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Batch(Model):
    request_id: UUID
    device_id: UUID
    recipient: str = Field(pattern=r'^\+?[0-9]{7,15}$')
    count: int = Field(default=10, ge=1, le=10)


class Binding(Model):
    job_id: UUID
    lease_id: UUID


class Claim(Model):
    worker_version: Literal[1, 2] = 1


class Send(Binding):
    subscription_id: int = Field(ge=0)


class Result(Binding):
    status: Literal['SENT', 'FAILED', 'UNKNOWN']
    result_code: int | None = None
    detail: str = Field(max_length=500)


class Delivery(Binding):
    delivery: Literal['DELIVERED', 'DELIVERY_FAILED']


def gate():
    if os.getenv('PHONE_SMS_TEST_ENABLED') != 'true' or os.getenv('ENVIRONMENT') == 'production':
        c.fail(503, 'Real SMS diagnostic queue disabled')


def create_batch(db, body, actor):
    gate()
    c.lock(db)
    old = c.row(db, 'SELECT * FROM phone_sms_batches WHERE request_id=:id', id=body.request_id)
    if old:
        if (old['device_id'], old['recipient'], old['count']) != (body.device_id, body.recipient, body.count):
            c.fail(409, 'Batch request ID already bound')
        return dict(batch_id=str(old['id']), count=old['count'])
    if not c.row(db, '''SELECT 1 FROM phone_worker_credentials f JOIN payout_devices d ON d.id=f.device_id
        WHERE f.device_id=:id AND NOT f.revoked AND d.enabled''', id=body.device_id):
        c.fail(409, 'Phone enrollment unavailable')
    batch = uuid4()
    c.run(db, '''INSERT INTO phone_sms_batches(id,request_id,device_id,recipient,count)
        VALUES(:id,:request,:device,:recipient,:count)''', id=batch, request=body.request_id,
        device=body.device_id, recipient=body.recipient, count=body.count)
    for n in range(1, body.count + 1):
        c.run(db, '''INSERT INTO phone_sms_jobs(id,batch_id,device_id,ordinal,recipient,message)
            VALUES(:id,:batch,:device,:n,:recipient,:message)''', id=uuid4(), batch=batch,
            device=body.device_id, n=n, recipient=body.recipient, message=f'Message {n}')
    c.audit(db, actor, 'REAL_SMS_BATCH_QUEUED', batch)
    return dict(batch_id=str(batch), count=body.count)


def wire(job):
    return dict(job_id=str(job['id']), batch_id=str(job['batch_id']), ordinal=job['ordinal'],
                recipient=job['recipient'], message=job['message'], status=job['status'],
                lease_id=str(job['lease_id']) if job['lease_id'] else None,
                kind='SMS_PAYOUT_TEST' if job.get('payout_id') else 'NUMBERED_TEST',
                payout_id=str(job['payout_id']) if job.get('payout_id') else None)


def claim(db, device, payment_capable=True):
    gate()
    c.lock(db)
    c.run(db, "UPDATE phone_worker_credentials SET last_seen_at=now(),state='SMS_WORKER' WHERE device_id=:id", id=device)
    active = c.row(db, "SELECT * FROM phone_sms_jobs WHERE device_id=:id AND status IN ('ASSIGNED','SENDING','UNKNOWN') FOR UPDATE", id=device)
    if active:
        if active['payout_id'] and not payment_capable:
            return dict(job=None, blocked=dict(wire(active), status='UPGRADE_REQUIRED'))
        if active['status'] != 'UNKNOWN' and active['lease_until'] <= datetime.now(timezone.utc):
            status = 'FAILED' if active['status'] == 'ASSIGNED' else 'UNKNOWN'
            active = c.row(db, '''UPDATE phone_sms_jobs SET status=:status,detail=:detail,updated_at=now()
                WHERE id=:id RETURNING *''', id=active['id'], status=status,
                detail='Expired before send authorization' if status == 'FAILED' else 'Send result missing; no automatic retry')
            complete_payment_test(db, active)
        if active['status'] == 'ASSIGNED':
            return dict(job=wire(active), blocked=None)
        if active['status'] in {'SENDING', 'UNKNOWN'}:
            return dict(job=None, blocked=wire(active))
    job = c.row(db, "SELECT * FROM phone_sms_jobs WHERE device_id=:id AND status='QUEUED' AND (:capable OR payout_id IS NULL) ORDER BY created_at,batch_id,ordinal LIMIT 1 FOR UPDATE", id=device, capable=payment_capable)
    if not job:
        return dict(job=None, blocked=None)
    job = c.row(db, '''UPDATE phone_sms_jobs SET status='ASSIGNED',lease_id=:lease,lease_until=:expires,updated_at=now()
        WHERE id=:id RETURNING *''', id=job['id'], lease=uuid4(), expires=datetime.now(timezone.utc) + timedelta(minutes=2))
    c.audit(db, device, 'SMS_ASSIGNED', job['id'])
    if job['payout_id']:
        payout = c.row(db, 'SELECT * FROM payouts WHERE id=:id FOR UPDATE', id=job['payout_id'])
        if payout['status'] == 'RECEIVED':
            c.change(db, payout, 'PROCESSING', device, 'SMS_TEST_ASSIGNED')
    return dict(job=wire(job), blocked=None)


def owned(db, device, body):
    c.lock(db)
    job = c.row(db, 'SELECT * FROM phone_sms_jobs WHERE id=:id AND device_id=:device AND lease_id=:lease FOR UPDATE',
                id=body.job_id, device=device, lease=body.lease_id)
    if not job:
        c.fail(403, 'SMS job ownership/lease mismatch')
    return job


def start(db, device, body):
    gate()
    job = owned(db, device, body)
    if job['status'] != 'ASSIGNED':
        return dict(can_send=False, status=job['status'])
    if job['lease_until'] <= datetime.now(timezone.utc):
        c.fail(409, 'SMS assignment expired before send')
    if job['payout_id']:
        payout = c.row(db, 'SELECT * FROM payouts WHERE id=:id', id=job['payout_id'])
        if payout['status'] not in {'RECEIVED', 'PROCESSING'}:
            c.run(db, "UPDATE phone_sms_jobs SET status='FAILED',detail='Payment cancelled before SMS',updated_at=now() WHERE id=:id", id=job['id'])
            return dict(can_send=False, status='FAILED')
    c.run(db, '''UPDATE phone_sms_jobs SET status='SENDING',subscription_id=:sim,
        lease_until=now()+interval '90 seconds',updated_at=now() WHERE id=:id''', id=job['id'], sim=body.subscription_id)
    c.audit(db, device, 'SMS_SEND_BOUNDARY', job['id'])
    return dict(can_send=True, status='SENDING')


def result(db, device, body):
    job = owned(db, device, body)
    if job['status'] in {'SENT', 'FAILED'}:
        if (job['status'], job['result_code'], job['detail']) != (body.status, body.result_code, body.detail):
            c.fail(409, 'Contradictory SMS result')
        return dict(accepted=True)
    if job['status'] not in {'SENDING', 'UNKNOWN'}:
        c.fail(409, 'SMS send boundary was not recorded')
    if body.status == 'SENT' and body.result_code != -1:
        c.fail(409, 'SENT requires Android RESULT_OK (-1)')
    if body.status == 'FAILED' and (body.result_code is None or body.result_code == -1):
        c.fail(409, 'FAILED requires an Android failure result')
    c.run(db, '''UPDATE phone_sms_jobs SET status=:status,result_code=:code,detail=:detail,updated_at=now()
        WHERE id=:id''', id=job['id'], status=body.status, code=body.result_code, detail=body.detail)
    c.audit(db, device, 'SMS_' + body.status, job['id'])
    complete_payment_test(db, job)
    return dict(accepted=True)


def install(router, phone, admin, get_db, transaction):
    @router.post('/admin/api/phone-workers/sms-batches')
    def batch(body: Batch, user=Depends(admin), db=Depends(get_db)):
        return transaction(db, create_batch, body, user['uid'])

    @router.get('/admin/api/phone-workers/sms-jobs')
    def jobs(user=Depends(admin), db=Depends(get_db)):
        return [dict(r) for r in c.run(db, 'SELECT * FROM phone_sms_jobs ORDER BY created_at DESC,ordinal LIMIT 100').mappings()]

    @router.post('/v1/sms/claim')
    def next_job(body: Claim | None = None, identity=Depends(phone), db=Depends(get_db)):
        return transaction(db, claim, identity[0]['device_id'], bool(body and body.worker_version == 2))

    @router.post('/v1/sms/start')
    def send(body: Send, identity=Depends(phone), db=Depends(get_db)):
        return transaction(db, start, identity[0]['device_id'], body)

    @router.post('/v1/sms/result')
    def report(body: Result, identity=Depends(phone), db=Depends(get_db)):
        return transaction(db, result, identity[0]['device_id'], body)

    @router.post('/v1/sms/delivery')
    def delivery(body: Delivery, identity=Depends(phone), db=Depends(get_db)):
        def execute(db):
            job = owned(db, identity[0]['device_id'], body)
            if job['status'] not in {'SENDING', 'SENT', 'UNKNOWN'}:
                c.fail(409, 'No submitted SMS')
            if job['delivery'] and job['delivery'] != body.delivery:
                c.fail(409, 'Contradictory delivery receipt')
            c.run(db, 'UPDATE phone_sms_jobs SET delivery=:delivery,updated_at=now() WHERE id=:id',
                  delivery=body.delivery, id=job['id'])
            return dict(accepted=True)
        return transaction(db, execute)
