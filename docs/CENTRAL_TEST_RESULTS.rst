Central backend verification — 9 October 2026
============================================

Environment
-----------

Windows 10 build 19045, four logical CPUs, Python 3.12.3, PostgreSQL 18.1.
PostgreSQL ran in a newly initialized temporary cluster bound to localhost port
55439, separate from the user's existing PostgreSQL service. Tests created uniquely
named databases and dropped their own databases afterward. No production database
or existing payout/funding data was migrated or modified.

The new service was tested in an isolated virtual environment installed from
``requirements-central.lock``. ``pip check`` reported no broken requirements.
Legacy tests used the established Python environment to avoid upgrading simulator
dependencies. Tests include actual PostgreSQL constraints and HTTP endpoint calls;
these are not SQLite substitutes for PostgreSQL concurrency tests.

Results
-------

* Central safety, migrations, concurrency, HTTP and worker tests:
  ``.venv-central/Scripts/python.exe -B -m pytest tests/test_central.py -q``.
  **25 passed**, 34.49 seconds.
* Existing simulator hardening and callback regressions, including the new legacy
  executor opt-in guard: **33 passed**, 6.15 seconds.
* Existing PostgreSQL integration suite, run through
  ``python -B tests/run_legacy_disposable.py``: **7 passed**, 6.88 seconds. This
  also exercised the complete legacy Alembic chain through the new central revision.

Total: **65 passed**. Syntax verification also passed for all 12 new Python files,
and whitespace checks passed for the modified existing source/documentation files.

Central coverage includes:

* 100 concurrent exact requests -> one payout, reservation and job.
* Changed key/reference instructions -> conflict; fresh keys map to original response;
  independent partners can reuse references; legitimate matching recipient/amount
  transfers with different references are accepted.
* Partner funds cannot be overspent concurrently; wallet float guards prevent claims.
* Concurrent claims cannot obtain multiple permissions for one phone/account/payout.
* Duplicate success events produce one payout journal and one PAID state event.
* Expired unarmed leases recover safely; armed expiry holds UNKNOWN with both reserves.
* Late results preserve evidence; old UNKNOWN/failed updates cannot overwrite PAID.
* UNKNOWN needs independent reviewers and evidence; non-payment decisions cannot
  contradict a recorded matching operator debit.
* Cancellation revokes arm permission; racing cancellation and arm have one winner.
* A crash before or after fake send never triggers a repeated send after reboot.
* Two local worker processes cannot execute the same journal command twice.
* Posted journals balance, reject mutation/later append, and retain rebuildable caches
  after disposing/reconnecting the database connection pool.
* Restricted runtime role can complete a payment but cannot edit ledger entries,
  journals or financial balance caches.
* Callback failure leaves payment execution independent.
* Statement imports are idempotent; debit suspense can be reclassified to a verified
  payout without booking a second wallet debit.
* A second reported receipt after PAID opens an incident without rewriting payment.
* HTTP acceptance commits before 202, replays original admission after PAID, and
  enforces tenant and worker scope. Full fake-worker HTTP protocol reaches PAID once.
* Recovery pause holds even restored CLAIMED attempts and blocks further arm calls.
* Both standalone and legacy migrations run successfully; standalone repeated
  upgrade is idempotent. Database tests use actual PostgreSQL 18.1.

Limits of this evidence
----------------------

No real phone, wallet or telecom payment was used. No production deployment occurred.
The 30-minute 10 requests/second target, one-minute 100 requests/second target, hardware
phone capacity and full PITR restore drill were not run. ``central/loadtest.py`` and
the runbook provide reproducible procedures. The recovery test exercises the recovery
state transition, not a complete backup restoration. Simulation success proves the
protocol/accounting path only, not the authenticity of a real operator payment.

Non-failing warnings: current Starlette prefers a newer HTTP test client integration;
the legacy environment warns about multipart import and naive datetime.utcnow usage.
The new service uses timezone-aware application timestamps and PostgreSQL timestamptz.
