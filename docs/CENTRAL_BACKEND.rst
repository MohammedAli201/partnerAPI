Central payout backend: review, implementation and operating contract
===================================================================

1. Assumptions and architecture
-------------------------------

The engineering prompt is treated as the requested specification. No production
deployment, real phone integration, or import of existing money balances is implied.
The inspected repository is a partner simulator: ``main.py`` is a large FastAPI
module, with public-schema payout/reservation/queue tables, signed callback retries,
and a UI. Existing work was preserved. The following findings prevent using that
simulator as the central financial service:

* ``decide_status`` accepts success words or a balance difference as proof of payment
  and returns FAILED for ambiguous outcomes. Neither is authoritative evidence.
* The legacy protocol has no durable arm boundary, attempt identity, device/wallet
  ownership, result inbox, or double-entry ledger. Expired work can be reclaimed.
* Admission returns existing references without comparing immutable instructions,
  has no HTTP idempotency record, and rejects matching recipient/amount requests.
* Legacy deposits and adjustments modify cached balances without ledger journals.

The new ``central`` package is a modular monolith backed by a single PostgreSQL 18
database, SQLAlchemy Core, FastAPI and Alembic. SQLAlchemy Core is intentional:
financial transitions and lock boundaries are explicit SQL. API, callback delivery
and reaper are separate processes; Raspberry Pis use authenticated HTTP only.
No broker is needed at the stated admission rate. There is no Android code or PIN.

The ``central`` schema is the new source of truth. Existing ``public`` tables and
the old UI remain the simulator. They do not share funding with central partners.
The legacy executor HTTP dependency is disabled by default; explicit development
use requires ``ENABLE_LEGACY_SIMULATOR_EXECUTOR=true``. Never attach real phones to
that protocol. Existing simulator endpoints retain their legacy behavior.

Prefunding is required. Insufficient partner funding rejects admission with 402
and rolls back payout, key, reservation and events. There is no WAITING_FUNDS queue.
Currencies USD/EUR/GBP have scale 2. Input is integer minor units, never rounded or
converted through float. There is no FX engine: funds and wallet must use the same
currency. The corridor indicates origin region and Somali destination, not an FX
instruction. Credit/postpaid would require explicit credit-limit reservations,
receivables, collections and settlement policy; changing a cached balance is unsafe.

Python 3.12 and PostgreSQL 18 were used for verification. The dedicated fully pinned
``requirements-central.lock`` was installed in ``.venv-central``. It includes
FastAPI 0.143.0, SQLAlchemy 2.1.4, psycopg 3.3.6 and Alembic 1.20.0. Legacy
dependencies were not upgraded. ``central/Dockerfile`` builds only the new service.

2. Relationships, DDL and migrations
------------------------------------

Executable full DDL is ``central/schema.sql``. All times are UTC-capable timestamptz.
Every accepted payout stays in one table through its lifecycle. Deduplication keys
and references are retained indefinitely; archiving must preserve these identities.

::

  partners ---< credentials
      |  \---< accounts ---< entries >--- journals
      |                              \--- payouts
      +---< payouts --- jobs                 |
                | \---< attempts >--- devices >--- workers
                |          |           |
                |          +--- wallets +--- wallets --- accounts
                +---< reservations >--- accounts
                +---< api_idempotency (composite tenant FK)
                +---< history
                +---< outbox --- deliveries
                +---< cases >--- reviewer credentials
                +--- receipts >--- wallets
  wallets ---< statement_imports ---< statement_items >--- payouts (optional)
  worker events --- inbox               all sensitive decisions --- audit
  controls: global/network/wallet pause configuration

Table purposes:

* partners: corridor, fee snapshot source, pause and configured callback destination.
* credentials: separately scoped hashed bearer tokens, revocation and identities.
* workers/devices/wallets: authenticated Pi, physical SIM ownership, liquidity,
  operator account identity, observed balance, limits and quarantine.
* accounts/journals/entries: balances rebuildable from immutable double-entry history.
* payouts: immutable typed instructions, canonical hash, tenant and versioned state.
* api_idempotency: synchronous partner inbox, permanent key/hash and stored response.
* jobs: durable queue, one row per payout, available time, generation and lease owner.
* attempts: immutable command and assignment, distinct execution phase and evidence.
* reservations: funding and float authorization; released history is retained.
* history/outbox/deliveries: state history, immutable status event and mutable delivery
  lease/backoff, including destination/secret snapshots for rotation consistency.
* inbox: stable authenticated worker event, payload hash, protected payload and response.
* receipts: verified provider identity, currently unique per operator wallet account.
* cases: independent proposal/approval for uncertain outcomes and incidents.
* statement_imports/items: idempotent operator debit ingestion and exact reference match.
* audit: redacted actions and protected evidence references; no PIN or inline USSD text.

Composite payout tenant/currency foreign keys protect reservations, idempotency and
outbox ownership. Reservation triggers also require the financial account's partner.
Partial unique indexes prevent unresolved duplicate payout, SIM and wallet attempts.
UNKNOWN remains unresolved. Receipt uniqueness is an assumption to confirm for each
operator: if receipts reset by day or account generation, change the scope before
connecting that operator. Never resolve a collision by silently ignoring a debit.

Choose ONE migration chain:

* New central service: set ``CENTRAL_DATABASE_URL`` to the migrator DSN, then run
  ``python -m central.migrate``. This has its own ``central_alembic_version`` table.
* Existing database already using this repository's legacy Alembic chain: run
  ``python -m alembic upgrade head``. Revision ``20261009_000003`` creates central.
  Do not run its baseline against an unversioned existing database.

Both consume identical DDL, but must not be interchanged after initial deployment.
Apply ``central/roles.sql`` once as migrator; provision a separate runtime LOGIN and
grant ``payout_runtime``. The API must not own tables or use a superuser. Ledger
entries/journals cannot be edited or deleted. The entry-cache trigger has a fixed
search path and controlled owner privileges; the API cannot edit balance caches.
There is no destructive financial downgrade. Take and verify a backup first.

3. API contracts and idempotency
--------------------------------

OpenAPI is served at ``/docs`` by ``central.app:app``. Credentials use
``Authorization: Bearer <independent high-entropy token>``. No partner_id is accepted
in request JSON; strict models reject unknown fields. Status, cancellation and
reports derive tenant identity from the credential. Revocation is stored in DB.
Credential provisioning/rotation currently uses reviewed administration SQL; there
is no credential management UI.

Admission:

.. code-block:: http

   POST /v1/payouts
   Authorization: Bearer <partner token>
   Idempotency-Key: partner-request-001
   Content-Type: application/json

   {"external_reference":"transfer-001","amount_minor":10000,"currency":"USD",
    "recipient":"+252611234567","network":"evc","corridor":"EU-SO"}

.. code-block:: json

   {"payout_id":"<uuid>","external_reference":"transfer-001","status":"QUEUED",
    "status_url":"/v1/payouts/<uuid>"}

202 follows admission COMMIT; it means accepted, not paid. Strings are trimmed,
currency/corridor uppercased and network lowercased. Reference case is preserved.
Recipient must already be E.164; country prefixes are never guessed. Supported
corridors are EU-SO, GB-SO and US-SO, additionally limited by each partner's list.
Keys are opaque and reject surrounding whitespace. Hash v1 is SHA-256 over compact
sorted JSON including version, reference and all immutable instructions.

Same partner/key or same partner/reference and same canonical instructions returns
the original admission response. A fresh key with an identical reference stores
another mapping to that payout. Changed instructions return 409 even after payment.
Different partners may use the same reference. Same recipient/amount with a NEW
reference creates another legitimate payout. There is no expiry policy for identity.
Admission uses INSERT ON CONFLICT DO NOTHING, never instruction-overwriting UPSERT.

``GET /v1/payouts/{id}`` returns live state, version, amounts, fee and hold reason.
``POST /v1/payouts/{id}/cancel`` revokes an unarmed claim and releases reservations.
``GET /v1/reports`` groups status/amount/fee by currency and reports available and
reserved funding. Fees on pending rows are snapshots; only PAID rows have recognized
fees. Settlement export and period-filtered reports remain a later integration.

Pi endpoints (credential determines worker_id):

* POST /internal/v1/claim, body ``{"device_id":"<uuid>"}``: one command or null,
  poll_after_seconds=3. Command includes payout/attempt/device/wallet IDs, minor-unit
  amount, currency, recipient, network, corridor, instruction hash and lease generation.
* POST /internal/v1/attempts/{id}/heartbeat: generation; extends lease by 120 seconds.
* POST /internal/v1/attempts/{id}/arm: generation and instruction_hash. Admission
  gates/reservations are checked again and ARMED is committed before HTTP permission.
* GET /internal/v1/attempts/{id}: worker-scoped immutable command and recorded phase.
* POST /internal/v1/results: stable event_id, attempt_id, generation, instruction_hash,
  outcome, stage, timezone-aware occurred_at, evidence_ref, optional provider_reference
  and simulator proof. Returns 202 after inbox/effects commit. Retries preserve the
  whole result, including timestamp and event ID; changed event content returns 409.

Outcomes: SUCCESS, DEFINITE_FAILURE_BEFORE_SEND, UNKNOWN. Stages: BEFORE_ARM,
BEFORE_SEND, AFTER_SEND, UNKNOWN. Worker messages do not independently prove payment.
Only explicit simulator mode with a verified command-bound HMAC can automatically
confirm PAID. Real SUCCESS currently becomes UNKNOWN and requires operator evidence.
The simulator secret is NEVER an operator verification mechanism.

Callbacks preserve event_id/status_version/payload across delivery retries. Signature:
HMAC-SHA256(secret, UTF8(timestamp + '.' + nonce + '.') + exact raw body). Headers:
X-Payout-Timestamp, X-Payout-Nonce, X-Payout-Signature. Receiver must verify signature,
clock window and fresh nonce, durably deduplicate event ID and acknowledge with 202.
No redirects are followed. Endpoints/secrets are administrator configured, not taken
from payout payloads. Global callback delivery does not block payment transactions.

Reviewer/admin APIs cover case listing/proposal/approval, statement debit import,
balance observation, confirmed funding/topup, pause switches, idle inspection,
webhook replay and metrics. Reviewer evidence references identify protected operator
records, not proof derived from a timeout or a missing statement line.

4. State and recovery tables
----------------------------

==================== ========================== ===============================
Transition           Actor/precondition         Effects/reservations/retry
==================== ========================== ===============================
new -> QUEUED        partner, valid/funded      reserve amount+fee, create job
QUEUED -> CLAIMED    eligible worker/SIM/wallet reserve wallet amount, lease
CLAIMED -> ARMED     live generation, all gates record arm BEFORE permission
CLAIMED -> QUEUED    reaper, never armed        resolve attempt, wallet release;
                                                partner retained, delayed retry
QUEUED/CLAIMED       partner before arm         revoke generation, release both,
  -> CANCELLED                                 terminal history/event
CLAIMED -> FAILED    authenticated BEFORE_ARM  release both, no automatic retry
ARMED -> PAID        verified fake receipt      capture both, ledger, event
ARMED -> UNKNOWN     ambiguous/unverified       retain both, quarantine SIM,
                                                hold job, unresolved attempt
CLAIMED -> UNKNOWN   recovery or late evidence  conservative hold, retain both
QUEUED -> ON_HOLD    dispatch retry limit       retain partner authorization
UNKNOWN -> PAID      independent reviewers      verified debit; capture, ledger
UNKNOWN -> FAILED    independent reviewers      proven non-payment + neutralized
                                                stale commands; release both
==================== ========================== ===============================

Validation/RECEIVED is synchronous and not persisted as an intermediate state.
ARMED is the public execution-risk state; attempt phases remain separate. A reaper
processes at most 50 expired leases per short transaction. Pre-arm retries use bounded
exponential delay plus jitter; five dispatches cause ON_HOLD. No timeout after arm
ever requeues, releases funding, changes phone, cancels or refunds automatically.
Operator rejection after arming currently also requires review: no operator contract
has proved it is safe to retry. Final states cannot be overwritten by older callbacks.

============================== ================================================
Failure/recovery point         Required action
============================== ================================================
admission rollback             no accepted payout or partial reservation
claim lost before arm          expiry can resolve pre-arm attempt and retry
arm reply lost                 local ARM_REQUESTED becomes UNKNOWN on restart
local mark before final send   MAY_HAVE_SUBMITTED is fsync-backed; crash -> UNKNOWN
phone paid, result lost         resend stable local result; NEVER repeat send
expired/stale result            persist evidence, reconcile; no stale overwrite
webhook unavailable             independent retries, stable event, capped backoff
database restored              global pause; quarantine unresolved attempts;
                               compare local journals + operator statements
unproven outcome                remain held indefinitely until evidence exists
============================== ================================================

The Pi journal is SQLite WAL with synchronous=FULL. Its compare-and-set prevents
duplicate local execution. It commits ARM_REQUESTED before HTTP arming, then
MAY_HAVE_SUBMITTED before irreversible confirmation. Already risky phases never send
again. Results persist before delivery and are retried until 202. The fake adapter
produces receipts only; it does not perform USSD or store wallet PINs. Hardware must
honor fsync. Back up the journal and never clone it onto another executing phone.

A backend lease cannot physically stop an old Pi pressing confirmation. Physical
ownership, stopping stale worker processes, SIM quarantine, and an inspected idle
phone are required before reuse. UNKNOWN blocks both phone and wallet account.
Case resolution leaves quarantine intact; inspect-idle is a separate audited action.

5. Transactions and executable claiming/posting
-----------------------------------------------

``central/service.py`` contains executable SQL and Python for all transitions.
``central/app.py`` explicitly uses ``with engine.begin()`` inside each handler so
commit finishes before returning. Dependency teardown is not used for admission.

Admission transaction: conflict-safe payout/idempotency resolution, available-funding
guard, partner reservation, job, history, outbox and callback destination snapshot.
Claim transaction: eligible device/wallet, ready job using FOR UPDATE SKIP LOCKED,
wallet-float guard/reservation, generation/owner/lease, immutable attempt and history.
Arm transaction: worker ownership/generation/live lease, partner/network/global/
wallet/device gates, observed float and limits, both active reservations, arm mark,
history/outbox. Result transaction: worker inbox identity/hash, evidence, verified
accounting/reservation/state/history/outbox effects, saved acknowledgement. Independent
approval performs the same accounting transition in one transaction.

No database transaction spans phone, HTTP callback or external statement fetching.
Callback claiming commits before network I/O; a generation guards acknowledgement.
Leases can cause repeated CALLBACK delivery, which is deliberately at least once.

All financial mutations currently take one PostgreSQL transaction advisory lock
610092026, then row locks. This intentionally simple lock order prevents deadlocks
and overspending for the initial fleet, but serializes short financial transactions.
SKIP LOCKED job SQL is already present; parallel financial throughput remains bounded
by the global lock. Benchmark before replacing it with per-partner/account locks.
The lock has NO exactly-once implication for physical USSD.

Fair dispatch prefers the partner with oldest last dispatch, then priority/FIFO.
One unresolved attempt per wallet intentionally serializes its operator account.
Unavailable float/arm gates return a conflict/funding response and retain safe state;
the initial implementation does not yet automatically resume ON_HOLD jobs or implement
measured circuit breakers. Use network/global/wallet pauses during an outage.

``post`` checks journal business identity and balanced integer entries. Deferred
database constraint triggers require a nonempty balanced journal per currency at
COMMIT. Append-only triggers reject edits/deletes and later additions to posted
journals. A controlled entry trigger updates normal-side caches transactionally.
Journal keys prevent duplicate economic effects; reused keys with changed effects
return 409. Rebuild caches from signed entries (credit-normal accounts invert sign).
Corrections must be new balanced journals. Do not set a balance to repair history.

6. Ledger examples and reconciliation rules
-------------------------------------------

Positive entry means debit; negative means credit. Asset balances are debit-normal;
partner payable and fee income are credit-normal. Example fee is fixed USD 0.60,
charged only on confirmed payment, with no operator fee assumed:

====================== ============================ ============================
Business event         Debit                        Credit
====================== ============================ ============================
prefund USD 200         bank asset 20000             partner payable 20000
topup wallet USD 150    wallet asset 15000           bank asset 15000
reserve USD 100+fee     no journal; partner 10060    no cash movement
assign wallet          no journal; wallet 10000     no cash movement
successful payout      partner payable 10060        wallet asset 10000;
                                                    fee income 60
pre-arm cancellation   no journal; release holds    no cash movement
UNKNOWN                no guessed payout journal    keep both reservations
unexpected debit 100   reconciliation suspense 10000 wallet asset 10000
verified unknown debit partner payable 10060        wallet 10000 + fee 60
====================== ============================ ============================

The last row posts only once. If an unmatched statement debit was already posted
to suspense, ``settle_paid`` first posts a balanced reclassification (debit wallet,
credit suspense), then the actual payout in the same transaction. This avoids
double accounting while preserving the actual external debit and its history.
Further physical debit with a different receipt is a new wallet loss/suspense
posting and quarantines the wallet. Constraints must not conceal it. A real refund
requires a separately evidenced correcting/reversal journal; no refund endpoint
or automatic reversal is implemented.

Statement ingestion currently accepts authoritative DEBIT records only. Import
identity is wallet/source plus content hash; item identity is wallet/operator reference.
Matching requires receipt identity plus amount, currency and recipient. Repeated
identities with conflicting fields reject the entire import. Missing records do not
prove failure. Matching unresolved attempts adds evidence for review; it never
automatically releases UNKNOWN. Unexpected debits are recorded against suspense,
disable the wallet and quarantine its devices. Posting real losses is allowed even
if wallet assets fall below held reservations; assignment guards prevent new spending.

UNKNOWN decisions require two distinct reviewer credentials. Proposal includes
verified operator evidence, decision, debit reference for PAID, and confirmation that
stale execution is neutralized. Approval checks independence and applies financial
effects once. Evidence authenticity is an operational responsibility until an operator
adapter is implemented. A missing receipt, screenshot, menu completion, timeout,
HTTP 200 or balance difference alone is insufficient. Unresolved cases remain held.
Statement credits, bank-statement ingestion and automated settlement matching remain
future adapters; do not feed already-booked wallet topups through the debit importer.

7. Capacity and scaling plan
----------------------------

10,000/86,400 = 0.11574 requests/second average. This says nothing about peak arrivals
or physical completion. Phone planning formula is phones * operating seconds /
seconds per payout; usable capacity multiplies the MEASURED usable fraction.

======================= =============== ================
Scenario at 60 sec      theoretical/day illustrative 70%
======================= =============== ================
5 phones, 24 hours      7200            5040
10 phones, 24 hours     14400           10080
10 phones, 16 hours     9600            6720
======================= =============== ================

These are scenarios, not guarantees. Ten phones at 70% for 24 hours leave almost no
spare capacity. Measure service-time percentiles, uptime, wallet/account limits,
burst demand, maintenance time and UNKNOWN rates. Five-minute completion depends
on queue age and peak utilization, not daily average. Scaling SIMs on one serialized
wallet will not increase that wallet's concurrency. Add independent eligible operator
accounts/phones only after measured bottlenecks justify them.

``python -m central.loadtest --rate 10 --seconds 1800 --out load-10.json`` and
``--rate 100 --seconds 60 --out load-100.json`` are proposed backend tests. They use
10% exact duplicate traffic, integer amounts, legitimate identical recipients, and
emit response/error counts, p50/p95/p99, duration and client hardware. Use a dedicated
funded partner with execution paused; provision enough available funds for all unique
requests. Record server hardware, workers, dataset and DB configuration alongside
the output. Do not confuse this with simulated phone completion. These full-duration
benchmarks were not run in this implementation session; no capacity claim is made.

8. Implementation stages, verification and operations
-----------------------------------------------------

Completed: source-of-truth DDL and two migration entry points; independent tenant and
worker authentication; canonical request/key/reference idempotency; admission and
funding guards; durable queue and fenced attempts; arm boundary; held uncertainty;
append-only ledger and reservations; inbox/outbox; signed independent callback
delivery; cancellation and safe pre-arm expiry; simulator local journal; reviewer
resolution; debit statement import/suspense; pause, reports, metrics and benchmark tool.

Tests use newly created uniquely named PostgreSQL databases on a separate disposable
cluster. They never reset the user's existing public schema. Migration upgrade is run
twice to verify replay. The test suite covers 100 concurrent duplicates, conflicting
instructions, isolated references, fund overspend, simultaneous claims, duplicate
success, lease expiry before/after arm, independent resolution, cancel/arm race,
ledger balance/immutability/cache rebuild, database reconnect, callback outage,
conservative recovery pause, wallet shortage, statement reclassification, HTTP
commit/replay/tenant checks, and worker crashes before/after fake send.

Commands:

.. code-block:: powershell

   python -m venv .venv-central
   .\.venv-central\Scripts\python.exe -m pip install -r requirements-central.lock
   $env:CENTRAL_DATABASE_URL='<migrator DSN>'
   .\.venv-central\Scripts\python.exe -m central.migrate
   # Provision payout_runtime and switch to its DSN before starting API.
   $env:CENTRAL_SIMULATOR_ENABLED='true' # development only
   $env:CENTRAL_SIMULATOR_SECRET='<separate random development secret>'
   .\.venv-central\Scripts\python.exe -m central.bootstrap
   # Save generated demo credentials privately; global execution is still paused.
   .\.venv-central\Scripts\python.exe -m uvicorn central.app:app --port 8001
   .\.venv-central\Scripts\python.exe -m central.processes callbacks
   .\.venv-central\Scripts\python.exe -m central.processes reaper
   $env:CENTRAL_WORKER_TOKEN='<generated worker token>'
   .\.venv-central\Scripts\python.exe -m central.simulator --device '<device UUID>'

Use the generated admin credential and POST /internal/v1/controls with scope global,
identity all, paused false and a reviewed reason ONLY after fixture/recovery checks.
Bootstrap is development-only and creates balanced simulated funding; never use its
artificial balances in a production database. Disable simulator mode in production.

Verification results are recorded in ``docs/CENTRAL_TEST_RESULTS.rst``. To reproduce,
set ``CENTRAL_TEST_CLUSTER_URL`` to an explicitly disposable PostgreSQL cluster on
which the test user can create/drop its OWN new databases, then run
``python -B -m pytest tests/test_central.py -q``. Without it, DB tests skip openly.
Existing simulator tests run separately with its established environment.

Metrics endpoint reports acceptance response counts/latency buckets (per process,
reset on restart), ready depth/oldest age, payout state age/count, hourly paid count,
device quarantine, expired leases, funding/float and observation differences, and
callback attempts. Export/aggregate metrics and add alert thresholds operationally.
Partner/network/wallet/global pause gates are checked immediately before arm.

Production staging still requires secret-manager references/encryption, TLS and
ingress limits, operator adapter validation, evidence-store access controls, complete
bank/credit/fee reconciliation, measured circuit breakers and observability export.
Partner callback destinations must be approved HTTPS addresses with outbound network
policy; stored callback signing secrets currently rely on restricted/encrypted DB
storage. Do not expose bootstrap or migrator credentials through the service.

Backup/restart runbook:

1. Configure encrypted base backups and continuous WAL archiving/PITR, with agreed
   RPO/RTO; preserve worker journals separately. Test restores on an isolated host.
2. Stop dispatch/arm traffic and isolate old workers BEFORE a database restore or
   risky restart. Restore into an isolated network, with no phone access.
3. Run ``python -m central.processes recovery-pause`` before exposing worker endpoints.
   It persists global pause and marks every unresolved attempt UNKNOWN, even a restored
   CLAIMED row: the backup may predate arming. Quarantine their devices.
4. Compare ALL worker journal attempts/receipts since the backup cutoff, operator
   debit statements and central history. A missing payout/attempt in the restored
   database also needs investigation; the service cannot discover it by itself.
5. Import authoritative evidence and resolve known outcomes with independent review.
   Check journal balance, cached balance rebuild, reservations and funding statements.
6. Stop/neutralize stale commands, inspect phones idle, enable only reconciled devices
   and wallets, and deliberately clear the global pause. Preserve unresolved holds.

Recovery pause is an explicit runbook step, not automatic restore detection. A database
backup can also restore an older global pause=false setting: never expose it before
the recovery command and external reconciliation. Test this whole operational process;
the automated test exercises the pause transition, not a complete PITR restoration.

9. Remaining limitations and required operator capabilities
------------------------------------------------------------

This is a tested central backend foundation and simulator, not a production-ready
payment processor. Real operator success is deliberately NOT auto-confirmed. To
resolve UNKNOWN automatically an operator must supply authenticated, complete,
queryable transaction records, scoped unique receipt/debit identity, recipient/amount/
currency/time, final outcome semantics and authoritative non-payment proof. It must
also provide a way to establish stale commands cannot later submit. Missing records
and silent USSD failures do not satisfy that contract.

Real phones require a tested adapter, durable journal hardware behavior, exclusive
physical ownership and explicit final-confirmation boundary. Local fake success
proofs test protocol behavior; they are not evidence about a telecom wallet.

Additional limits: initial global financial serialization; no measured capacity or
automatic circuit breaker; no FX/postpaid credit; no operator charge model; no automatic
held-job resume; debit-only statement import; no settlement CSV/UI; reviewer assertions
are not cryptographically verified operator data; no scheduled backup implementation
or full PITR drill; evidence/webhook secrets require stronger storage integration;
legacy UI remains separate. These are deployment gates, not claimed implemented features.

Pattern references:
https://www.postgresql.org/docs/current/ddl-constraints.html
https://www.postgresql.org/docs/current/sql-select.html
https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html
