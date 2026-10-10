End-to-end partner and USSD software simulation
==============================================

This runs the existing main:app routes through actual HTTP, not a replacement
payment service. It provisions Atlas EU (6000), Britannia UK (2500), Liberty USA
(1000) and Nordic EU (500) through /admin/create-partner, two-user zero opening
reviews and ledger prefunding. Worker/device/wallet fixtures use reviewed direct
SQL because there is no administrative provisioning API yet. All amounts are
integer minor units and synthetic. Prefunding is calculated before execution;
each physical wallet is funded separately with an identified synthetic opening.

Run from partnerCodeApi on Windows/PowerShell:

  .\.venv-central\Scripts\python.exe -m pip install -r requirements-payout.lock
  .\.venv-central\Scripts\python.exe -B -m simulation.run --profile mixed --period 120 --phones 10

The environment needs local PostgreSQL binaries, defaulting to
C:\Program Files\PostgreSQL\18\bin. Set SIMULATION_PG_BIN to override that
binary directory. The runner creates its OWN fresh loopback-only PostgreSQL
cluster and UUID-named database, applies migrations, verifies an ownership marker,
starts two API processes, a local receiver, eight callback delivery threads and
the normal lease reaper. It stops only its owned processes/cluster afterwards.
It never accepts a target production database or truncates an existing database.
Run data remains under ignored .simulation-runs/<run UUID>/ for inspection.

Other separate 10,000-instruction profiles:

  .\.venv-central\Scripts\python.exe -B -m simulation.run --profile burst --phones 10
  .\.venv-central\Scripts\python.exe -B -m simulation.run --profile spread --period 600 --phones 5

Each invocation creates a separate run ID, manifest, database and credentials.
Only scenarios explicitly identified in the results document have been executed.
Do not present the runnable burst/spread profiles as measured results unless run.

Timing controls: --concurrency (default 64), --connections (96), --timeout (30),
--drain-timeout (3600), --period (120), --app-workers (2). Each partner receives
one quarter of the client slots so the largest initial burst cannot monopolize
all client slots. The initial mixed burst releases 6000 jobs at scheduled time
zero; it does not assert 6000 simultaneous network requests. Remaining 4000
jobs have fixed-seed independent jitter and additional short bursts over 120s.
Pass --partner-config simulation/example-config.json to configure each partner's
period/jitter and receiver failure/acknowledgement behavior independently.
The backend's real 600/minute and 20/second partner limits remain enabled.
Rate-limited/time-out requests retry the SAME reference/idempotency key. Their
waiting time is reported; quotas make a 120-second complete admission impossible
for Atlas's 6000 payouts. No quota is silently increased for simulation.

Execution modes: --mode accelerated --accelerated-delay .002 is software-test
timing, while --mode realistic --session-seconds 30 models longer sessions. Delayed
confirmation lasts three times the configured duration, with real heartbeats.
Realistic mode needs a longer --drain-timeout (e.g. 86400) and is not measured
unless explicitly reported. Accelerated throughput is not a real phone SLA.

The deterministic initial allocation is 8500 success, 500 definitive pre-arm
failure, 500 safe pre-arm retries, 300 possibly-submitted unknown, 200 delayed
success. The intended final states are SENT=9200, FAILED=500, UNKNOWN=300.
Half the unknown cases actually debit the independent simulated operator ledger;
the backend remains uncertain about all 300 and retains both funding holds.
The expected operator effect count is therefore 9350, while financial completed
payout journals are exactly 9200. Neither success nor final payout counts are
forced by changing payout rows. Outcomes use the real worker API.

A real 120-second lease is allowed to expire once before arm and once after
possible submission. The normal reaper handles both; no payout/queue rows are
edited to force the intended outcomes. Duplicate and stale worker results are
submitted over HTTP. A durable worker journal is closed/reopened after an operator
debit to simulate restart, recovering UNKNOWN without replaying a payment.
The restart fault is logical worker restart, not an OS process kill or DB power
failure. All worker journals and the operator record use SQLite WAL/FULL sync.

New controls needed for a runnable safe simulation
------------------------------------------------

RETRYABLE_FAILURE_BEFORE_SEND is accepted only for a live CLAIMED attempt with
BEFORE_ARM stage. It releases the physical wallet reservation, retains partner
funding, closes the attempt and queues a fenced new generation after two seconds.
A retryable assertion after ARM becomes UNKNOWN; it cannot release or resend.

Revision 005 adds execution_closed_at and independent containment reviews.
Unresolved UNKNOWN remains unique per payout and retains its financial case and
reservations. Initially it still blocks the phone/wallet. To reuse the phone,
two different active administrators must approve durable evidence that the old
physical session is neutralized and independently measured float is recorded:

  POST /admin/api/attempts/{attempt_id}/containment/propose
  POST /admin/api/containment/{review_id}/approve

That closes ONLY physical ownership, never the financial attempt/case, never
changes UNKNOWN, and never makes that payout dispatchable again. Unique indexes
still prevent simultaneous uncontained execution on a device or wallet. The
simulation's independent operator store records reset/neutralization and observed
float; two simulated admin identities then use these actual protected APIs.
Real deployments must obtain genuine physical/operator evidence before approval.
This is not automatic timeout-based device unquarantining. Later financial
recognition of a contained payment does not debit the already verified physical
float a second time. Production startup requires revision 005 and refuses
PAYOUT_SIMULATOR_ENABLED=true.

The first development run exposed a query-plan bottleneck: claim's fairness
subquery scanned execution history once per candidate queue row. It now aggregates
last-dispatch time once per partner and joins that result. Callback TLS contexts
are reusable while retaining certificate/hostname verification. The local test
relay uses a thread-local persistent HTTP client. No production authentication
or destination checks were weakened to improve load numbers.

Webhook receiver and transport boundary
---------------------------------------

The receiver is an actual HTTP service bound to 127.0.0.1. It verifies the exact
body HMAC with the partner-specific secret and 300-second header freshness,
commits receipt before acknowledgement, stores attempts separately, deduplicates
stable event IDs and prevents out-of-order status regression. Atlas responds 202;
Britannia deterministically returns selected first-attempt 500s; Liberty injects
503s and waits beyond the sender deadline AFTER committing selected events;
Nordic delays acknowledgements and returns 202. Fault selection uses synthetic
recipient/status rather than random event ID, so repeated fixtures exercise the
same fault classes. An actual invalid-signature request must return 401.

Production rejects private/loopback webhook destinations. simulation.backend
therefore has an explicit confined transport relay mapping exactly four registered
*.simulation.invalid URLs to this owned loopback receiver. It requires ENVIRONMENT
simulation, a matching UUID database marker and payout_e2e_ database on 127.0.0.1.
It cannot route arbitrary destinations. Only this separate test entry point imports
the adapter; normal main:app does not. Actual body/signatures/outbox claims/retries/
leases travel over HTTP. This harness does NOT test TLS certificates/DNS/IP pinning
through that relay; existing security tests exercise the production transport.
No external partner services are contacted or internal credentials forwarded.

Evidence and assertions
-----------------------

credentials.json contains SIMULATION-ONLY API/worker/webhook credentials, remains
ignored and is never copied into reports. Do not commit or share it. report.json
contains configuration, counts, timing percentiles, all failed assertion names,
HTTP classifications, per-partner funding/receipt outcomes and fault results.
manifest.json retains scheduled time, actual client start, response/admission
completion, queue delay and worker terminal time for every instruction.
http-attempts.json records every actual HTTP attempt/response or transport failure
and each probe's expected code without headers/secrets/request body.
Four *-events.sqlite3 files store per-partner unique receipts and delivery attempts;
operator.sqlite3 independently stores payment effects and physical sessions;
phone-*.sqlite3 retain durable worker command journals. Component logs are private
run artifacts and do not log credential-bearing responses.

Every run asserts 10,000 business payouts, requested partner totals, all additional
1000 duplicate/100 conflict/100 invalid/100 isolation/100 malformed probes,
DB reference uniqueness, 10,000 reservations, 10,500 execution attempts,
9200 confirmed payout journals, no duplicate operator effect, exact financial
projections, retained unknown holds, released failed holds, no CLAIMED/ARMED or
unexpected pending jobs, history/outbox equivalence, all outbox events delivered
to their own partner once logically, correct final receiver states and every fault.
Unknown cases are expected outstanding evidence, not unexpected stuck work.

If assertions fail, report.json lists them and the command exits nonzero. Earlier
startup/interrupted development runs are labeled failures/interrupted and must not
be counted as successful scenarios. JSON summary and readable measured results
are saved separately from private credential/evidence files.
