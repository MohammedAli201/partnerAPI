"""Payment admission and test accounting for the real SMS worker queue."""
import json
import os
import re
from uuid import UUID

import backend_core as c


def payment_execution(db, payout):
    job = c.row(db, 'SELECT * FROM phone_sms_jobs WHERE payout_id=:id', id=payout)
    if not job:
        return None
    return dict(mode='SMS_TEST', payment_executed=False, job_id=str(job['id']),
                device_id=str(job['device_id']), sms_recipient=job['recipient'],
                sms_status=job['status'], sms_delivery=job['delivery'], detail=job['detail'])


def enqueue_payment(db, payout):
    if os.getenv('SMS_PAYOUT_TEST_ENABLED') != 'true':
        return None
    from sms_worker import Batch, create_batch, gate
    gate()
    # Admission already holds the global transaction lock. This allocation and
    # the payment insert commit together, or both roll back.
    instructions = c.stored_instructions(payout)
    # The public payout provider EVC routes to the enrolled Hormuud/EVC device.
    worker_provider = 'hormuud' if instructions['provider'] == 'evc' else instructions['provider']
    device = c.row(db, '''SELECT d.id FROM payout_devices d
        JOIN phone_worker_credentials f ON f.device_id=d.id
        LEFT JOIN phone_sms_jobs j ON j.device_id=d.id AND j.status IN ('QUEUED','ASSIGNED','SENDING','UNKNOWN')
        WHERE d.enabled AND NOT f.revoked AND lower(d.provider)=:provider AND lower(d.network)=:network
        GROUP BY d.id ORDER BY count(j.id),d.id LIMIT 1''',
        provider=worker_provider, network=instructions['network'])
    if not device:
        c.fail(503, 'No enrolled SMS test worker matches the payment provider/network')
    recipient = os.getenv('SMS_PAYOUT_TEST_RECIPIENT', '97368681')
    if recipient == 'payment-recipient':
        recipient = payout['recipient']
    if not re.fullmatch(r'\+?[0-9]{7,15}', recipient):
        c.fail(503, 'Invalid configured SMS test recipient')
    batch = create_batch(db, Batch(request_id=payout['id'], device_id=device['id'],
                                   recipient=recipient, count=1), 'payout-admission')
    reference = re.sub(r'[^A-Za-z0-9_-]', '?', payout['partner_tx_id'])[:20]
    message = f"SMS TEST {reference} | {payout['amount']:.2f} {payout['currency']} | {str(payout['id'])[:8]}"
    c.run(db, '''UPDATE phone_sms_jobs SET payout_id=:payout,message=:message WHERE batch_id=:batch''',
          payout=payout['id'], message=message, batch=UUID(batch['batch_id']))
    # This explicit SMS substitute must never also enter the money-transfer queue.
    c.run(db, "UPDATE payout_queue SET status='HELD' WHERE payout_id=:id", id=payout['id'])
    c.audit(db, device['id'], 'PAYOUT_SMS_TEST_QUEUED', payout['id'])
    return payment_execution(db, payout['id'])


def complete_payment_test(db, job):
    if not job.get('payout_id'):
        return
    payout = c.row(db, 'SELECT * FROM payouts WHERE id=:id FOR UPDATE', id=job['payout_id'])
    job = c.row(db, 'SELECT * FROM phone_sms_jobs WHERE id=:id', id=job['id'])
    if json.loads(payout['request_payload'] or '{}').get('sms_test_accounting') and os.getenv('ENVIRONMENT') != 'production':
        if payout['status'] in {'SENT', 'FAILED', 'CANCELLED', 'REJECTED'}:
            return
        if job['status'] == 'UNKNOWN':
            c.change(db, payout, 'UNKNOWN', job['device_id'], 'SMS_TEST_SEND_UNCERTAIN')
            return
        if job['status'] == 'SENT':
            reservation, payable = c.release_partner(db, payout, True)
            amount = c.minor(payout['amount'], payout['currency'])
            fee = c.minor(reservation['fee'], payout['currency'])
            clearing = c.account(db, f"sms-test-clearing:{payout['currency']}", 'SUSPENSE', payout['currency'])
            fees = c.account(db, f"sms-test-fees:{payout['currency']}", 'FEES', payout['currency'])
            entries = [(payable['id'], amount + fee), (clearing['id'], -amount)]
            if fee:
                entries.append((fees['id'], -fee))
            c.post(db, f"sms-test-payout:{payout['id']}", 'PAYOUT', payout['currency'], entries,
                   f"sms-test:{job['id']}:android-result-ok", payout['id'])
            status, reason = 'SENT', 'SMS_TEST_SUCCESS_NO_MONEY_TRANSFER'
        else:
            c.release_partner(db, payout)
            status, reason = 'FAILED', 'SMS_TEST_SEND_FAILED'
        c.run(db, "UPDATE payout_queue SET status='DONE' WHERE payout_id=:id", id=payout['id'])
        c.change(db, payout, status, job['device_id'], reason)
        return
    # SMS is a substitute for execution, not a transfer or a fee-earning payment.
    if c.row(db, "SELECT 1 FROM payout_reservations WHERE payout_id=:id AND status='ACTIVE'", id=payout['id']):
        c.release_partner(db, payout)
    c.run(db, "UPDATE payout_queue SET status='DONE' WHERE payout_id=:id", id=payout['id'])
    if payout['status'] in {'RECEIVED', 'PROCESSING'}:
        c.change(db, payout, 'CANCELLED', job['device_id'], 'SMS_TEST_ONLY_NO_MONEY_TRANSFER')
