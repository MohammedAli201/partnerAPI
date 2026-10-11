# Architecture

- `app`: enrollment and operator controls, foreground SMS service, real SMS sender,
  callback receiver and manual USSD diagnostics.
- `data`: authenticated HTTP transport, Android Keystore encryption, protected
  enrollment settings and Room history/outbox for legacy execution reports.
- `device`: readiness checks and the disabled real payment accessibility adapter.
- `domain`: legacy payment state machine, immutable instructions and recovery rules.
  Retained to report existing history; no runtime simulator adapter is wired.

`SmsQueueWorker` owns the active SMS session and encrypted local send records.
A local send boundary is persisted before calling SmsManager. Backend authorization
is consumed once. Sent and delivery broadcasts save their result before uploading.
Periodic WorkManager uploads recover reports after a connection failure.

The backend owns assignment, leases, one active slot per phone, payout reservations
and test accounting. SMS queue operations live in `sms_worker.py`; linked payment
admission and accounting live in `sms_payout.py`. Enrollment and USSD diagnostics
live in `phone_worker.py`. All linked state changes commit in one DB transaction.
