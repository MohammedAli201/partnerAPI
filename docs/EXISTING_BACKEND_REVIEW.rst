Existing partner-facing backend review
======================================

Scope and verified findings
---------------------------

This work modifies main:app. Public partners/payouts/queue remain authoritative.
The following findings were verified in the pre-hardening working tree; references
name the implementation points rather than obsolete line numbers:

* security.py generate_api_key/verify_api_key: salted PBKDF2-SHA256, 120,000
  iterations. Confirmed. Old verifiers remain supported without weaker checking.
* models.py Payout and baseline migration: (partner_id,partner_tx_id) uniqueness.
  Confirmed; an additional canonical UUID alias now prevents date-prefix bypass.
* main.py create_payout: payout, reservation, queue and balance updates were one
  commit with SELECT FOR UPDATE on the partner. Confirmed; locking did protect
  available money, but did not make an execution timeout safe to retry.
* middleware.py limiter and old main.py decorators: submission quotas used remote
  IP and in-memory process counters. Confirmed; shared DB quotas now replace them.
* payout_webhooks.py old deliver_next: claimed ORM events and performed delivery
  before the session transaction finished. Confirmed; registered_webhooks.py now
  commits its lease before DNS or socket I/O, then guards the result separately.
* auth_session.py old URLSafeSerializer/read_session: no timestamp max_age or
  server session revocation; cookie max_age alone did not enforce authorization.
  Confirmed. browser_security.py enforces both DB and signed timestamp limits.
* main.py old duplicate path: returned existing reference without a full immutable
  instruction comparison; a nearby recipient/amount heuristic could also suppress
  distinct legitimate payouts. Confirmed; backend_core.admission replaces both.
* main.py funding routes and balance_transactions: balances/history, no balanced
  double-entry accounting. Confirmed; journal entries now drive projections.

Implemented behavior and compatibility
--------------------------------------

POST /payouts-create retains HTTP 201 and response field names. Every retry checks
recipient, exact minor amount, scale-2 currency, provider, network, corridor and
canonical external UUID. Identical references return the existing payout; changed
instructions or HTTP idempotency keys return 409. Idempotency-Key is optional;
when supplied the original response is replayed even after settlement. Independent
references with identical recipient/amount remain legitimate transactions.
Partner identity comes only from current API authentication; status, cancellation,
reports and endpoint lookup filter by that authenticated identity.

Supported funding currencies are USD/EUR/GBP, one reviewed funding currency per
partner. No FX or unmodeled currency conversion is performed. Worker commands
contain only immutable executable fields; incidental metadata is not executable.

Registered endpoints require HTTPS on 443, no credentials/fragments, publicly
routable IPv4/IPv6. Registration records resolved addresses. Delivery validates
DNS again and connects to an approved numeric address with original hostname
TLS verification/SNI; redirects are never followed. DNS changes block delivery
until reapproval. Old arbitrary destinations become BLOCKED; register the actual
partner endpoint and manually replay retained events. Per-payout callback_url
is accepted only if exactly equal to the registered endpoint. Outbound headers
use that partner's HMAC secret, fresh timestamp/nonce, stable signed body/event ID;
no internal executor token/global API key is forwarded. Partners must deduplicate
notification event IDs and authenticate the exact byte sequence.

Sessions use a signed DB session ID and hashed CSRF token, 12-hour absolute and
30-minute idle expiration, current role/is_active checks and server logout.
Production cookies are Secure/HttpOnly/SameSite=Lax (readable CSRF cookie is
separate). Unsafe cookie requests require X-CSRF-Token; cross-site origins are
rejected. Login has origin checks and shared user/IP throttles. Existing sessions
are invalidated by the format change and require login. CORS defaults to no
external origins; configure only approved origins. HTTPS must be enforced upstream.

Ledger journals/entries and financial evidence are append-only; deferred DB
constraints reject unbalanced or empty postings and late appends. Business event
keys prevent duplicate postings. Available/reserved old balance columns are DB
maintained projections after enablement. Financial transitions, reservation
resolution, journals, history and outgoing events commit together. Distinct
partner funding and physical wallet assets are never treated as interchangeable.
Opening/correction approval requires a different active administrator.

Worker contract
---------------

Independent worker credentials authenticate claim, heartbeat, arm, result and
status under /internal/workers/v2. Device/SIM/wallet bindings and unique unresolved
attempt indexes prevent overlapping backend ownership. Commands include payout,
attempt, device, wallet, generation, immutable instruction hash and instructions.
ARM permission is committed before being returned. The durable simulator journal
uses SQLite WAL/FULL synchronization and refuses resend after uncertain permission
or possible submission, including reboot. No phone/Android automation was added.

Expired unarmed claims can safely release wallet reservations and retry with a
new generation. Armed, legacy PROCESSING, or possibly submitted work becomes
UNKNOWN, holds partner AND wallet reservations and quarantines the device.
No automatic switch of phones or funding release follows a timeout. Simulator
success requires explicit opt-in and a command-bound proof. Real SUCCESS reports
are evidence and remain UNKNOWN until two administrators approve current provider
receipt/nonpayment evidence and confirm the stale physical worker cannot submit.
A lease does not physically prevent a phone confirmation. Duplicate/late evidence
is retained without a second journal or final-state regression. A distinct extra
receipt opens an incident. Database triggers fence attempt instruction mutation.

Limits and authentication
-------------------------

Shared PostgreSQL fixed windows apply across processes/instances: submissions
600/minute and 20/second per partner; status polling 1800/minute and 60/second;
reports 120/minute and 10/second. Separate peer-IP protection is 12000/minute;
login 20/minute per IP and 10/minute per username. Browser operations have
1800 reads/minute and 240 writes/minute per authenticated user. Fixed windows
allow edge-of-window bursts. Forwarded headers are not blindly trusted; configure
proxy trust to avoid treating every partner as the same proxy address.

New random API keys have 256 bits of entropy and a keyed HMAC-SHA256 verifier
when API_KEY_VERIFIER_SECRET is configured (at least 32 random characters).
Constant-time comparison remains. Legacy PBKDF2 verification is unchanged;
rotation explicitly replaces/revokes old credentials. No silently accepted weak
key migration is used. Pepper rotation requires coordinated credential migration;
changing it immediately invalidates current HMAC keys. Keep it separate from
session and webhook secrets. Production startup requires configured strong secrets.

Migration and operation
-----------------------

Revision 004 is additive over the existing 001/002/003 chain. Revision 003 is now a reserved no-op; new upgrades do not install the unused
separate-service schema. Already-created local draft schemas are preserved. Legacy
balances, funding history, evidence and payout rows are retained. Old PROCESSING
and leased jobs are conservatively UNKNOWN/HELD with reconciliation cases.
Old RECEIVED jobs without canonical instructions are held for a reviewed
legacy adapter before dispatch; admission retries still resolve their reference.
No retrospective synthetic transactions are invented. Partners start ledger_disabled
until evidence matches available/reserved balances and active reservations and
an independent approval posts an explicitly named opening journal. Canonical
reference collisions prevent enabling the account. The new reservation tenant FK
is NOT VALID for legacy rows; investigate old anomalies before VALIDATE CONSTRAINT.

Before rollout: rehearse upgrade on an anonymized restored snapshot, reconcile
every partner/currency, review legacy UNKNOWN executions and wallet float, register
approved endpoints, provision independent worker credentials/device bindings and
review wallet opening postings. Back up and rehearse recovery. Run migrations with
a separate owner. Apply payment_roles.sql and use a separate restricted runtime
login (never the owner/superuser), keeping secrets in the deployment secret store.
The runtime role can insert balanced posts but cannot rewrite/delete financial
history. Application authorization still matters for who may create corrections.

Use requirements-payout.lock for reproducible dependencies. Docker/Fly run the
existing main app with two Uvicorn processes. Callback and reaper process groups
run independently of HTTP; Fly autostop is disabled. Each app process pool is 8
plus 4 overflow, so budget aggregate app/callback/reaper/admin DB connections.
No production migration, deployment or real payout has been performed here.

After restoring a backup, keep execution paused and run payment_processes recovery
before permitting workers; it holds unresolved attempts for reconciliation. A
restore can lose execution evidence: do not infer nonpayment from absent records.
Add outbound firewall restrictions to complement approved-address pinning, enforce
TLS to remote PostgreSQL, secret encryption/rotation, monitored backups and alerts
for UNKNOWN, oldest queue age, callback retries, reservation drift and ledger
imbalance. Retention/data access policy for recipient/provider evidence must be
set before production operation.

Remaining material limitations
------------------------------

Operator receipt verification is currently independent human review, not an
operator API/import adapter. Legacy UNKNOWN cases without a new attempt, extra
debit incidents, and restoring physical wallet mismatches require that adapter
or a separately reviewed recovery procedure; the API refuses unsafe resolution.
Contradictory late evidence from a resolved pre-arm attempt freezes current
ownership and disables the old wallet pending physical balance review.
Worker/device/wallet provisioning currently requires reviewed DB administration;
no complete administrative provisioning UI is implemented. Provider fees/FX,
operator-specific settlement rules and regulatory controls remain outside this
phase. Never create a wallet opening from an assumed balance.

The initial financial posting path uses one short global advisory lock for simple
lock ordering. Its burst performance must be judged from measurements; sharding
this lock requires documented resource ordering and repeated concurrency tests.
Local short benchmarks are not Fly measurements or a sustained soak. No physical
phone capacity is claimed. This system is not labeled production-ready.

Validation and measured capacity
--------------------------------

See tests/test_existing_backend.py and tests/test_existing_http.py for actual
PostgreSQL and HTTP regressions, tests/test_payout_webhooks.py for wire compatibility,
and docs/existing-benchmark.json for raw measured results. Superseded tests that
required automatic lease resend/global callback credentials were replaced by
safe-protocol regressions, not retained as an alternative execution path.
The earlier central suite tests unused code and is not evidence of this app's
admission capacity. Ten thousand/day averages 0.116 requests/second, but the
contractual burst, polling, callback backlog and physical wallet/phone capacity
must be sized independently. See docs/EXISTING_CAPACITY.rst for both benchmark runs, failures and
measurement-based staging resource recommendations.
