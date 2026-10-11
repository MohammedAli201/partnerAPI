Android PayoutWorker and Hubaal
==============================

Hubaal serves enrolled phone APIs at /v1 in main:app. The real SIM diagnostic
uses Android TelephonyManager.sendUssdRequest; the backend stores actual carrier
responses separately from payout accounting.

Simulator cleanup
-----------------

Runnable fake-worker scripts, the multi-phone simulation harness, its mock
backend/receiver, synthetic provisioning and fake-worker launch commands have
been removed from this project. Local simulator execution flags are disabled.
Legacy /v1/claim returns 503 and does not create simulated assignments.
Historical migrations, database evidence and deterministic unit-test fixtures
remain. Test fixtures have no HTTP clients or worker entry points.

Setup
-----

Install requirements-payout.lock and run python -m alembic upgrade head using
the migration-owner database account. Configure .phone-worker-local.json with
DATABASE_URL, ENVIRONMENT=development, independent SECRET_KEY and
API_KEY_VERIFIER_SECRET, PHONE_WORKER_ENABLED=true, PHONE_USSD_TEST_ENABLED=true
and EMBEDDED_PAYMENT_WORKERS=false. Keep this ignored configuration private.

start_phone_worker.ps1 starts the persistent local backend.
stop_phone_worker.ps1 stops its supervisor and owned server.
manage_phone_worker.ps1 devices lists existing devices.
manage_phone_worker.ps1 code --device <UUID> issues a single-use enrollment code.
manage_phone_worker.ps1 control --device <UUID> --action pause controls the phone.
These commands do not create fake workers or synthetic funding.

Real SIM diagnostic
-------------------

Enroll/unlock the updated Android app and use Real SIM USSD test. Enter a
nine-digit Somali mobile number, load the backend instruction and run it on
Android's default call SIM. No simulated payout is required.

POST /v1/ussd-tests/standalone accepts request_id (UUID) and recipient (nine digits).
Hubaal returns the fixed-format *125*recipient# instruction. The app saves the
request ID before loading and calls the modem after operator confirmation.
POST /v1/ussd-tests/result records REQUESTED, RESPONDED, FAILED or UNKNOWN with
the actual carrier message in PostgreSQL. A response is not proof of payment.
Repeated loads return the same test. Issued requests are never automatically
resent. New test explicitly starts another diagnostic after a terminal result.

GET /admin/api/phone-workers/ussd-tests lists diagnostic records for administrators.
Standalone records have no payout attempt and post no payment ledger entries.
An empty balance may produce a carrier rejection. A SIM without network
registration may fail before receiving a response. Interactive PIN/menu replies
are not automated.

The local database may contain historical synthetic payouts from earlier tests;
cleanup does not relabel those records as real payments or delete their evidence.

Real SMS queue test
-------------------

Set PHONE_SMS_TEST_ENABLED=true in the non-production phone host environment.
POST /admin/api/phone-workers/sms-batches accepts a unique request_id, existing
device_id, recipient and count (1 through 10). It creates numbered Message 1?10
jobs atomically. Repeating the same request_id never creates another batch.
The real Android app uses /v1/sms/claim, /v1/sms/start, /v1/sms/result and
/v1/sms/delivery. One active job per device is enforced by both row locking and
a unique database index. The next job waits for the preceding send result to
be saved. SENT is Android's successful sent callback, not recipient delivery.
Delivery receipts are stored separately when the carrier supplies them.

Install the updated APK, unlock operator controls, grant SMS permission and
enable Automatic SMS worker. The app accepts numbered diagnostics and linked
SMS_TEST payment instructions and uses Android's default SMS SIM. A foreground
notification keeps the session visible. Local send state is persisted before
the modem call. Lost callback, crash or uncertain send holds the queue and does
not resend. Starting a session again recovers result reporting, not sending.
Stop after current SMS prevents further claims and finishes tracking the active
send. Inspect /admin/api/phone-workers/sms-jobs for the persisted job statuses.

Automatic payment SMS substitute
--------------------------------

In development, enable PHONE_SMS_TEST_ENABLED=true and
SMS_PAYOUT_TEST_ENABLED=true. SMS_PAYOUT_TEST_RECIPIENT=97368681 sends tests to
the agreed test number; payment-recipient selects each payment's recipient.
Apply all migrations through 000014 before enabling this mode.

An authenticated POST /payouts-create from Insomnia admits the payment and
creates exactly one linked SMS job in the same transaction. It selects an
enrolled device matching provider/network, holding monetary execution. No
matching device rejects admission with 503 and rolls back the reservation.
Use a full UUID partner_tx_id and an Idempotency-Key for safe request replay.

The updated app remains waiting when the queue is empty and claims each new
job automatically. Enable it once; no per-payment confirmation is required.
Only one SMS is active on a phone. A known result advances to the next job;
an uncertain send holds the queue without automatic resend. Android restart
recovery restores reporting and the enabled service where permitted. Reopen
the app after force-stop, and keep the backend and phone connection available.

GET /payouts/{id} includes execution.mode=SMS_TEST, sms_status, sms_delivery,
sms_recipient and payment_executed=false. Completing the test releases the
partner reservation and sets the monetary payout to CANCELLED with reason
SMS_TEST_ONLY_NO_MONEY_TRANSFER. SMS SENT or DELIVERED never means money paid.
This substitute is rejected in production. Older APKs cannot claim linked
payment jobs; install PayoutWorker-Automatic-SMS.apk first.

For a full accounting rehearsal, SMS_PAYOUT_TEST_ACCOUNTING=true stamps new
admissions for test settlement. A confirmed SMS SENT callback sets payout SENT,
captures the reservation and debits the partner by amount plus fee. The amount
credits an SMS-test clearing account and the fee credits an SMS-test fee account.
Earnings appear under activity=simulation. No SIM wallet is debited and
payment_executed remains false. Repeated callbacks cannot debit or earn twice.
UNKNOWN holds the reservation pending a known result; FAILED releases it.
Previously admitted jobs retain their original accounting behavior.

In development SMS mode, the exact example callback URL
https://partner.example.com/webhooks/payout-status is accepted without endpoint
registration. It is preserved in payment metadata; status events are stored
locally as BLOCKED with no delivery endpoint. Other callbacks still require a
matching registered partner endpoint. Production behavior is unchanged.
