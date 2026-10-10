Verification results, 2026-10-09
================================

Final command, Python 3.12.3 with requirements-payout.lock installed:

  python -B -m pytest tests -q --tb=short --disable-warnings --maxfail=5

Result: 70 passed, 9 warnings in 59.25 seconds. Of these, 45 exercise the existing
backend/HTTP compatibility/migration and 25 exercise the unused earlier central
implementation. The latter are not evidence of the existing backend's capacity.
Warnings concern framework/client and existing deprecation notices; no test was
marked failed. PostgreSQL-backed tests ran, rather than being skipped.

Tests used UUID-named disposable databases on PostgreSQL 18.1 at local port 55439.
Only those databases were created/truncated/dropped. The existing project/production
database was not used, migrated or reset. The disposable cluster was stopped after
verification. No real payouts, external partner callbacks or deployment occurred.

Existing-backend evidence covers concurrent duplicate admission, changed immutable
instructions, overspending, independent references, authenticated tenant status/
cancellation boundaries, sessions/roles/expiry/revocation/CSRF, SSRF and DNS rebinding,
no callback row lock during delivery, retained retry body and rollback atomicity,
shared partner quotas with 20 accepted/40 rejected concurrent calls, migration
conservation, restricted runtime role posting and denied history/cache edits,
balanced/append-only journals, command immutability, rejected settlement without
journal/receipt/capture/outbox, repeated receipt accounting, arm/expiry/cancellation,
UNKNOWN reservations, stale-result ownership freezing and durable fake-worker reboot.

Functional regressions are not a load benchmark. Actual two-process HTTP load
measurements and their failures are documented in EXISTING_CAPACITY.rst with raw
existing-benchmark.json and existing-benchmark-mixed.json. No daily soak or Fly
hardware capacity claim has been made.
