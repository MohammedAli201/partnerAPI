"""PayoutWorker v1 compatibility on Hubaal's existing PostgreSQL queue.

Real SIM diagnostic instructions and responses use the existing enrolled phone.
Legacy simulated payout assignments are retired. SMS jobs use their own durable
diagnostic queue and link to existing payouts for development accounting.
"""
import base64
import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt

import backend_core as c
import payment_worker as w

TRANSITIONS = {
    'QUEUED': {'RECEIVED'},
    'RECEIVED': {'VALIDATED', 'CONFIRMED_NOT_PAID', 'RECONCILIATION_REQUIRED'},
    'VALIDATED': {'READY', 'CONFIRMED_NOT_PAID', 'RECONCILIATION_REQUIRED'},
    'READY': {'PREPARING', 'CONFIRMED_NOT_PAID', 'RECONCILIATION_REQUIRED'},
    'PREPARING': {'SUBMISSION_POSSIBLE', 'CONFIRMED_NOT_PAID', 'RECONCILIATION_REQUIRED'},
    'SUBMISSION_POSSIBLE': {'AWAITING_CONFIRMATION', 'UNKNOWN', 'RECONCILIATION_REQUIRED'},
    'AWAITING_CONFIRMATION': {'CONFIRMED_SUCCESS', 'CONFIRMED_NOT_PAID', 'UNKNOWN', 'RECONCILIATION_REQUIRED'},
    'UNKNOWN': {'RECONCILIATION_REQUIRED'},
    'RECONCILIATION_REQUIRED': {'CONFIRMED_SUCCESS', 'CONFIRMED_NOT_PAID'},
    'CONFIRMED_SUCCESS': set(), 'CONFIRMED_NOT_PAID': set(),
}


def now():
    return datetime.now(timezone.utc)


def millis(value):
    return int(value.timestamp() * 1000)


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def payload_hash(job):
    # Exact Android Assignment.immutableHash(): byte lengths, fixed field order.
    name = job.get('recipient_name')
    fields = ['1' if name is None else '2'] + [str(job[key]) for key in (
        'payout_id', 'attempt_id', 'device_id', 'assignment_version', 'provider_id',
        'payout_account_id', 'sim_subscription_id', 'recipient', 'recipient_type',
        'amount_minor', 'currency', 'flow_version', 'claim_expires_at',
        'execution_expires_at', 'correlation_id', 'scenario')]
    if name is not None:
        fields.append(name)
    return token_hash(''.join(f'{len(value.encode())}:{value}' for value in fields))


def enabled():
    if not option('PHONE_WORKER_ENABLED', 'phone_worker_enabled') or environment() == 'production':
        c.fail(503, 'PayoutWorker integration is disabled')


def environment():
    if 'ENVIRONMENT' in os.environ:
        return os.environ['ENVIRONMENT']
    from config import get_settings
    return get_settings().environment


def option(name, setting):
    if name in os.environ:
        return os.environ[name] == 'true'
    from config import get_settings
    return getattr(get_settings(), setting)


def verify_signature(public_key, message, signature):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    try:
        key = serialization.load_der_public_key(base64.b64decode(public_key, validate=True))
        if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
            raise ValueError('P-256 required')
        key.verify(base64.b64decode(signature, validate=True), message.encode(), ec.ECDSA(hashes.SHA256()))
    except Exception:
        c.fail(401, 'INVALID_PROOF')


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Enroll(Model):
    code: str = Field(min_length=6, max_length=100)
    public_key: str = Field(max_length=1024)
    signature: str = Field(max_length=512)


class Renew(Model):
    device_id: UUID
    refresh_token: str = Field(max_length=200)
    signature: str = Field(max_length=512)


class Binding(Model):
    attempt_id: UUID
    payload_hash: str = Field(pattern='^[0-9a-f]{64}$')
    assignment_version: StrictInt = Field(gt=0)


class Heartbeat(Model):
    state: str = Field(max_length=64)
    app_version: str = Field(max_length=64)
    flow_version: Literal['sim-v1','evc-712-v1']


class Claim(Model):
    wait_seconds: int = Field(default=20, ge=1, le=25)


class StandaloneUssd(Model):
    request_id: UUID
    recipient: str = Field(pattern=r'^[0-9]{9}$')


class Evidence(Model):
    kind: Literal['SUCCESS_CONFIRMED', 'NOT_PAID_CONFIRMED', 'UNKNOWN']
    code: str = Field(max_length=100)
    reference: str | None = Field(default=None, max_length=256)
    payload_hash: str | None = Field(default=None, max_length=64)
    amount_minor: StrictInt | None = None
    currency: str | None = Field(default=None, max_length=3)
    carrier_response: str | None = Field(default=None, max_length=4096)


class EvcConfigure(Model):
    sim_subscription_id: StrictInt = Field(ge=0)


class Event(Binding):
    event_id: UUID
    payout_id: UUID
    sequence: StrictInt = Field(ge=1)
    phase: str = Field(max_length=64)
    at: StrictInt = Field(ge=0, le=4102444800000)
    schema_version: Literal[1] = 1
    evidence: Evidence | None = None


class NewCode(Model):
    device_id: UUID


class UssdResult(Model):
    test_id: UUID
    status: Literal['REQUESTED', 'RESPONDED', 'FAILED', 'UNKNOWN']
    response: str | None = Field(default=None, max_length=2000)


class DeviceControl(Model):
    device_id: UUID
    action: Literal['pause', 'resume', 'drain', 'undrain', 'revoke', 'unquarantine']


def device_info(db, device_id):
    d = c.row(db, '''SELECT d.*,w.enabled AS worker_enabled,w.simulator FROM payout_devices d
        JOIN payment_workers w ON w.id=d.worker_id WHERE d.id=:id''', id=device_id)
    # Payout worker execution may be retired while its enrolled physical phone
    # continues to authenticate for diagnostics and historical event uploads.
    if not d or not d['enabled']:
        c.fail(403, 'Simulator worker/device unavailable')
    return d, dict(id=d['worker_id'], simulator=d['simulator'],enabled=d['worker_enabled'])


def issue(db, device):
    access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    expires = now() + timedelta(minutes=15)
    c.run(db, '''UPDATE phone_worker_credentials SET access_hash=:access,refresh_hash=:refresh,
        access_expires_at=:expires,refresh_expires_at=:refresh_expires WHERE device_id=:id''',
        id=device['id'], access=token_hash(access), refresh=token_hash(refresh), expires=expires,
        refresh_expires=now() + timedelta(hours=24))
    cfg=dict(device_id=str(device['id']),provider_id='simulator',payout_account_id=str(device['wallet_id']),sim_subscription_id=-1,simulation=True)
    if not device['simulator'] and device['network'].lower()=='evc':
        from phone_evc import config
        cfg=config(db,device)
    return dict(access_token=access,refresh_token=refresh,expires_at=millis(expires),config=cfg)


def enrollment_code(db, device_id, actor):
    enabled()
    c.lock(db)
    device_info(db, device_id)
    if c.row(db, 'SELECT 1 FROM phone_worker_credentials WHERE device_id=:id', id=device_id):
        c.fail(409, 'Device already enrolled; credential renewal or explicit recovery required')
    code = secrets.token_urlsafe(12)
    expires = now() + timedelta(minutes=5)
    c.run(db, '''INSERT INTO phone_enrollment_codes(code_hash,device_id,expires_at,created_by)
        VALUES(:hash,:id,:expires,:actor)''', hash=token_hash(code), id=device_id, expires=expires, actor=str(actor))
    c.audit(db, actor, 'PHONE_ENROLLMENT_CODE', device_id)
    return dict(code=code, expires_at=millis(expires), device_id=str(device_id))


def authenticate(db, authorization):
    enabled()
    c.lock(db)
    if not authorization.startswith('Bearer ') or len(authorization[7:]) < 32:
        c.fail(401, 'AUTH_REQUIRED')
    credential = c.row(db, '''SELECT * FROM phone_worker_credentials
        WHERE access_hash=:hash AND NOT revoked AND access_expires_at>now() FOR UPDATE''',
        hash=token_hash(authorization[7:]))
    if not credential:
        c.fail(401, 'EXPIRED_OR_REVOKED')
    device, worker = device_info(db, credential['device_id'])
    return credential, device, worker


def controls(db, credential, device):
    wallet = c.row(db, 'SELECT * FROM payout_wallets WHERE id=:id', id=device['wallet_id'])
    paused = credential['paused'] or device['quarantined'] or not wallet['enabled']
    for scope, identity in [('global', 'all'), ('network', device['network']), ('wallet', str(device['wallet_id']))]:
        paused = paused or bool(c.row(db, 'SELECT 1 FROM payment_controls WHERE scope=:scope AND identity=:identity AND paused', scope=scope, identity=identity))
    return dict(paused=bool(paused), drain=credential['drain'], revoked=credential['revoked'])


def bound(db, binding, credential):
    assignment = c.row(db, '''SELECT * FROM phone_worker_assignments
        WHERE attempt_id=:id AND device_id=:device FOR UPDATE''', id=binding.attempt_id, device=credential['device_id'])
    if not assignment:
        c.fail(403, 'WRONG_DEVICE')
    job = assignment['payload']
    if binding.payload_hash != job['payload_hash'] or binding.assignment_version != job['assignment_version']:
        c.fail(409, 'PAYLOAD_CONFLICT')
    return assignment, job


def validate_evidence(job, evidence, phase, previous):
    if not evidence:
        c.fail(409, 'EVIDENCE_REQUIRED')
    if (phase == 'CONFIRMED_NOT_PAID' and evidence.code == 'LOCAL_NO_SUBMISSION'
            and evidence.kind == 'NOT_PAID_CONFIRMED'
            and previous in {'RECEIVED', 'VALIDATED', 'READY', 'PREPARING'}):
        return
    success = phase == 'CONFIRMED_SUCCESS'
    if (evidence.kind != ('SUCCESS_CONFIRMED' if success else 'NOT_PAID_CONFIRMED')
            or evidence.code != ('SIM_CONFIRMED' if success else 'SIM_REJECTED')
            or evidence.reference != 'SIM-' + job['attempt_id'] or evidence.payload_hash != job['payload_hash']
            or evidence.amount_minor != job['amount_minor'] or evidence.currency != job['currency']):
        c.fail(409, 'EVIDENCE_MISMATCH')


def reconciled(db, assignment, job):
    case = c.row(db, '''SELECT * FROM reconciliation_cases WHERE payout_id=:id
        AND resolved_at IS NOT NULL AND approver IS NOT NULL ORDER BY resolved_at DESC LIMIT 1''', id=UUID(job['payout_id']))
    attempt = c.row(db, 'SELECT * FROM payout_attempts WHERE id=:id', id=assignment['attempt_id'])
    payout = c.row(db, 'SELECT status FROM payouts WHERE id=:id', id=UUID(job['payout_id']))
    if not case or not attempt['resolved_at'] or payout['status'] not in {'SENT', 'FAILED'}:
        return dict(resolved=False, audit_id=None, evidence=None)
    success = payout['status'] == 'SENT'
    evidence = dict(kind='SUCCESS_CONFIRMED' if success else 'NOT_PAID_CONFIRMED',
                    code='SIM_CONFIRMED' if success else 'SIM_REJECTED', reference='SIM-' + job['attempt_id'],
                    payload_hash=job['payload_hash'], amount_minor=job['amount_minor'], currency=job['currency'])
    return dict(resolved=True, audit_id=str(case['id']), evidence=evidence)


def receive_event(db, event, credential, worker):
    assignment, job = bound(db, event, credential)
    body = event.model_dump(mode='json', exclude_none=True)
    if str(event.payout_id) != job['payout_id']:
        c.fail(409, 'EVENT_BINDING')
    hashed = c.digest(body)
    old = c.row(db, 'SELECT * FROM phone_worker_events WHERE event_id=:id', id=event.event_id)
    if old:
        if old['payload_hash'] != hashed or old['attempt_id'] != event.attempt_id:
            c.fail(409, 'EVENT_CONFLICT')
        return dict(ack_event_id=str(event.event_id))
    if event.sequence != assignment['sequence'] + 1:
        c.fail(409, 'EXPECTED_SEQUENCE_' + str(assignment['sequence'] + 1))
    if event.phase not in TRANSITIONS[assignment['phase']]:
        c.fail(409, 'ILLEGAL_TRANSITION')
    if event.phase == 'SUBMISSION_POSSIBLE' and not assignment['authorization_id']:
        c.fail(409, 'NO_AUTHORIZATION')
    if job['provider_id']=='evc-plus':
        from phone_evc import receive
        return receive(db,event,credential,worker,assignment,job,hashed)
    attempt, payout, queue = w.owned(db, worker, event.attempt_id, event.assignment_version, False)
    terminal = event.phase in {'CONFIRMED_SUCCESS', 'CONFIRMED_NOT_PAID'}
    if terminal:
        validate_evidence(job, event.evidence, event.phase, assignment['phase'])
        if assignment['phase'] == 'RECONCILIATION_REQUIRED':
            answer = reconciled(db, assignment, job)
            if not answer['resolved'] or answer['evidence']['kind'] != event.evidence.kind:
                c.fail(409, 'INDEPENDENT_AUDIT_REQUIRED')
        else:
            reference = event.evidence.reference
            report = dict(attempt_id=str(event.attempt_id), event_id=str(event.event_id),
                          lease_generation=event.assignment_version, instruction_hash=attempt['instruction_hash'],
                          outcome='UNKNOWN', stage='AFTER_SEND', provider_reference=reference,
                          evidence_ref='android://events/' + str(event.event_id),
                          occurred_at=datetime.fromtimestamp(event.at / 1000, timezone.utc).isoformat(), proof=None)
            if event.evidence.code == 'LOCAL_NO_SUBMISSION' and not assignment['authorization_id']:
                report.update(outcome='DEFINITE_FAILURE_BEFORE_SEND', stage='BEFORE_ARM')
            if report:
                w.result(db, worker, report)
    elif event.phase in {'UNKNOWN', 'RECONCILIATION_REQUIRED'}:
        w.unknown(db, attempt, payout, worker['id'], 'PHONE_' + event.phase)
    c.run(db, '''INSERT INTO phone_worker_events(event_id,attempt_id,sequence,payload_hash,payload)
        VALUES(:id,:attempt,:seq,:hash,CAST(:payload AS jsonb))''', id=event.event_id, attempt=event.attempt_id,
        seq=event.sequence, hash=hashed, payload=c.canonical(body))
    c.run(db, 'UPDATE phone_worker_assignments SET phase=:phase,sequence=:seq WHERE attempt_id=:id',
          id=event.attempt_id, phase=event.phase, seq=event.sequence)
    return dict(ack_event_id=str(event.event_id))


def make_router(get_db, require_role):
    router = APIRouter(tags=['PayoutWorker phone'])
    admin = require_role('admin')

    def transaction(db, function, *args):
        try:
            answer = function(db, *args)
            db.commit()
            return answer
        except Exception:
            db.rollback()
            raise

    def phone(authorization: str = Header(default=''), db=Depends(get_db)):
        return authenticate(db, authorization)

    import sms_worker
    sms_worker.install(router, phone, admin, get_db, transaction)

    @router.post('/v1/enroll')
    def enroll(body: Enroll, db=Depends(get_db)):
        def execute(db):
            enabled()
            verify_signature(body.public_key, 'enroll:' + body.code, body.signature)
            c.lock(db)
            code = c.row(db, '''SELECT * FROM phone_enrollment_codes WHERE code_hash=:hash
                AND used_at IS NULL AND expires_at>now() FOR UPDATE''', hash=token_hash(body.code))
            if not code:
                c.fail(401, 'CODE_EXPIRED_OR_USED')
            device, _ = device_info(db, code['device_id'])
            if c.row(db, 'SELECT 1 FROM phone_worker_credentials WHERE device_id=:id', id=device['id']):
                c.fail(409, 'DEVICE_ALREADY_ENROLLED')
            c.run(db, '''INSERT INTO phone_worker_credentials(device_id,public_key,access_hash,refresh_hash,access_expires_at,refresh_expires_at)
                VALUES(:id,:pub,:access,:refresh,now(),now())''', id=device['id'], pub=body.public_key,
                access=token_hash(secrets.token_urlsafe(32)), refresh=token_hash(secrets.token_urlsafe(32)))
            c.run(db, 'UPDATE phone_enrollment_codes SET used_at=now() WHERE code_hash=:hash', hash=token_hash(body.code))
            c.audit(db, device['worker_id'], 'PHONE_ENROLLED', device['id'])
            return issue(db, device)
        return transaction(db, execute)

    @router.post('/v1/renew')
    def renew(body: Renew, db=Depends(get_db)):
        def execute(db):
            enabled()
            c.lock(db)
            credential = c.row(db, '''SELECT * FROM phone_worker_credentials WHERE device_id=:id
                AND NOT revoked AND refresh_expires_at>now() FOR UPDATE''', id=body.device_id)
            if not credential or not secrets.compare_digest(credential['refresh_hash'], token_hash(body.refresh_token)):
                c.fail(401, 'RENEWAL_REJECTED')
            verify_signature(credential['public_key'], 'renew:' + body.refresh_token, body.signature)
            device, _ = device_info(db, body.device_id)
            return issue(db, device)
        return transaction(db, execute)

    @router.post('/v1/heartbeat')
    def heartbeat(body: Heartbeat, identity=Depends(phone), db=Depends(get_db)):
        credential, device, worker = identity
        c.run(db, 'UPDATE phone_worker_credentials SET state=:state,last_seen_at=now() WHERE device_id=:id', state=body.state, id=device['id'])
        c.run(db, 'UPDATE payment_workers SET heartbeat_at=now() WHERE id=:id', id=worker['id'])
        answer = controls(db, credential, device)
        db.commit()
        return answer

    @router.post('/v1/claim')
    def claim(body: Claim, identity=Depends(phone), db=Depends(get_db)):
        # Immediate polling is valid under the Android contract; no sleeping with DB locks held.
        if option('PHONE_EVC_PAYMENTS_ENABLED','phone_evc_payments_enabled'):
            from phone_evc import claim as real_claim
            return transaction(db,real_claim,identity)
        c.fail(503, 'Simulated assignments retired; real EVC execution is disabled')

    @router.post('/v1/evc/configure')
    def evc_configure(body: EvcConfigure, identity=Depends(phone),db=Depends(get_db)):
        from phone_evc import configure
        return transaction(db,configure,identity[1],identity[2],body.sim_subscription_id)

    @router.post('/v1/assignment/ack')
    def ack(body: Binding, identity=Depends(phone), db=Depends(get_db)):
        def execute(db):
            assignment, _ = bound(db, body, identity[0])
            w.owned(db, identity[2], body.attempt_id, body.assignment_version)
            c.run(db, 'UPDATE phone_worker_assignments SET acked=true WHERE attempt_id=:id', id=assignment['attempt_id'])
            return dict(accepted=True)
        return transaction(db, execute)

    @router.post('/v1/authorize')
    def authorize(body: Binding, identity=Depends(phone), db=Depends(get_db)):
        if option('PHONE_EVC_PAYMENTS_ENABLED','phone_evc_payments_enabled'):
            from phone_evc import authorize as real_authorize
            return transaction(db,real_authorize,body,identity)
        c.fail(503, 'Legacy simulated execution retired; use real SIM diagnostics')

    @router.post('/v1/events')
    def events(body: Event, identity=Depends(phone), db=Depends(get_db)):
        return transaction(db, receive_event, body, identity[0], identity[2])

    @router.post('/v1/reconcile')
    def reconcile(body: Binding, identity=Depends(phone), db=Depends(get_db)):
        def execute(db):
            assignment, job = bound(db, body, identity[0])
            return reconciled(db, assignment, job)
        return transaction(db, execute)

    @router.post('/v1/ussd-tests/standalone')
    def standalone_ussd(body: StandaloneUssd, identity=Depends(phone), db=Depends(get_db)):
        def execute(db):
            if not option('PHONE_USSD_TEST_ENABLED', 'phone_ussd_test_enabled'):
                c.fail(503, 'Manual USSD diagnostics disabled')
            c.lock(db)
            device = identity[0]['device_id']
            command = '*125*' + body.recipient + '#'
            old = c.row(db, 'SELECT * FROM phone_ussd_tests WHERE device_id=:device AND request_id=:request',
                        device=device, request=body.request_id)
            if old:
                if old['command'] != command:
                    c.fail(409, 'Request identifier already bound to another command')
                if old['status'] == 'CREATED' and old['expires_at'] <= now():
                    old = c.row(db, 'UPDATE phone_ussd_tests SET expires_at=:expires WHERE id=:id RETURNING *',
                                id=old['id'], expires=now() + timedelta(minutes=2))
                return ussd_record(old)
            record = c.row(db, '''INSERT INTO phone_ussd_tests(id,device_id,request_id,command,expires_at)
                VALUES(:id,:device,:request,:command,:expires) RETURNING *''', id=uuid4(), device=device,
                request=body.request_id, command=command, expires=now() + timedelta(minutes=2))
            c.audit(db, identity[2]['id'], 'REAL_SIM_TEST_PREPARED', record['id'])
            return ussd_record(record)
        return transaction(db, execute)

    @router.post('/v1/ussd-tests/result')
    def ussd_result(body: UssdResult, identity=Depends(phone), db=Depends(get_db)):
        def execute(db):
            record = c.row(db, 'SELECT * FROM phone_ussd_tests WHERE id=:id AND device_id=:device FOR UPDATE',
                           id=body.test_id, device=identity[0]['device_id'])
            if not record:
                c.fail(403, 'WRONG_DEVICE')
            if record['status'] == body.status and record['response'] == body.response:
                return dict(accepted=True)
            if record['status'] in {'RESPONDED', 'FAILED', 'UNKNOWN'}:
                c.fail(409, 'Diagnostic already recorded; never automatically execute again')
            if body.status == 'REQUESTED':
                if record['status'] != 'CREATED' or record['expires_at'] <= now() or body.response is not None:
                    c.fail(409, 'Test expired or already requested')
            elif record['status'] != 'REQUESTED':
                c.fail(409, 'Record the request boundary before its result')
            c.run(db, 'UPDATE phone_ussd_tests SET status=:status,response=:response,updated_at=now() WHERE id=:id',
                  id=body.test_id, status=body.status, response=body.response)
            c.audit(db, identity[2]['id'], 'MANUAL_USSD_' + body.status, body.test_id)
            return dict(accepted=True)
        return transaction(db, execute)

    @router.post('/admin/api/phone-workers/enrollment-codes')
    def new_code(body: NewCode, user=Depends(admin), db=Depends(get_db)):
        return transaction(db, enrollment_code, body.device_id, user['uid'])

    @router.get('/admin/api/phone-workers')
    def devices(user=Depends(admin), db=Depends(get_db)):
        return [dict(row) for row in c.run(db, '''SELECT d.id,d.worker_id,d.wallet_id,d.provider,d.network,d.enabled,d.quarantined,
            f.paused,f.drain,f.revoked,f.last_seen_at,f.state FROM payout_devices d JOIN phone_worker_credentials f ON f.device_id=d.id''').mappings()]

    @router.get('/admin/api/phone-workers/ussd-tests')
    def ussd_tests(user=Depends(admin), db=Depends(get_db)):
        return [dict(row) for row in c.run(db, '''SELECT t.*,a.payout_id FROM phone_ussd_tests t
            LEFT JOIN payout_attempts a ON a.id=t.attempt_id ORDER BY t.created_at DESC LIMIT 100''').mappings()]

    @router.post('/admin/api/phone-workers/control')
    def control(body: DeviceControl, user=Depends(admin), db=Depends(get_db)):
        return transaction(db, device_control, body.device_id, body.action, user['uid'])

    return router


def ussd_record(record):
    return dict(test_id=str(record['id']), command=record['command'], status=record['status'],
                response=record['response'], expires_at=millis(record['expires_at']))


def device_control(db, device_id, action, actor):
    c.lock(db)
    if not c.row(db, 'SELECT 1 FROM phone_worker_credentials WHERE device_id=:id', id=device_id):
        c.fail(404, 'Phone not enrolled')
    if action == 'unquarantine':
        if c.row(db, 'SELECT 1 FROM payout_attempts WHERE device_id=:id AND resolved_at IS NULL', id=device_id):
            c.fail(409, 'Resolve outstanding attempts before clearing quarantine')
        c.run(db, 'UPDATE payout_devices SET quarantined=false WHERE id=:id', id=device_id)
    else:
        field, value = {'pause': ('paused', True), 'resume': ('paused', False), 'drain': ('drain', True),
                        'undrain': ('drain', False), 'revoke': ('revoked', True)}[action]
        c.run(db, f'UPDATE phone_worker_credentials SET {field}=:value WHERE device_id=:id', id=device_id, value=value)
    c.audit(db, actor, 'PHONE_' + action.upper(), device_id)
    return dict(accepted=True)
