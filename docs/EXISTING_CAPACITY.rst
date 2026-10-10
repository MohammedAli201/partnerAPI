Local measured admission capacity
=================================

Measured 2026-10-09 on Windows 10, Python 3.12.3, 4 logical CPUs, 16,239 MiB
host memory. Two actual Uvicorn HTTP processes, PostgreSQL 18.1 on the same host,
128 MB shared_buffers and max_connections=100. Each app process pool was 8 + 4
overflow. Ten authenticated partners, synthetic prefunding, exact USD 1.00 payouts
plus USD 0.60 fee. Every accepted submission was polled; 10% of jobs additionally
retried the same payout and sent invalid credentials. A separate callback thread
injected alternating one-second 202 responses and one-second unavailable endpoints.
No real funds, phones, external callbacks or production database were involved.

Measured scenarios
------------------

Mixed existing keys: four PBKDF2 partners and six HMAC partners:

* 10 scheduled submissions/second for 20 seconds: 200/200 new submissions, 20/20
  duplicate retries and 200/200 polls succeeded. 20 invalid keys returned 401.
  Total drain 20.14 seconds; completion rate 9.93 new submissions/second.
  Submission p50/p95/p99: 54/402/453 ms; poll p95 367 ms.
* 100/second for 10 seconds: 999 received 201, one submission and two polls timed
  out at the client. 100 duplicate retries succeeded, invalid keys returned 401.
  Drain 127.96 seconds; completion rate 7.82/second INCLUDING the submission
  timeout. Submission p95 23.46 seconds. This fails a 100/second capacity claim.
* Heavy single partner, 100/second for 5 seconds: 475 submissions returned 201,
  10 returned contractual 429 and 15 returned 402 because this first run's partner
  had only USD 1000 synthetic funding. These are legitimate rejections, not
  successful throughput. The fixture was subsequently funded more generously.

Explicitly rotated random HMAC keys for all ten partners, with sufficient funds:

* 10/second for 20 seconds: all 200 submissions and 20 retries succeeded; 199
  polls succeeded and one timed out. Submission p50/p95/p99: 37/61/104 ms.
  Because the poll timeout delayed completion, drain was 30.28 seconds. Do not
  conceal that failure behind the lower submission percentiles.
* 100/second for 10 seconds: all 1000 submissions, 100 retries and 1000 polls
  succeeded, 100 invalid keys returned 401. Drain was 67.79 seconds, or 14.75
  completed new submissions/second. Submission p95 12.20 seconds, poll p95 13.32
  seconds. Accepting the backlog does not demonstrate 100/second sustained capacity.
* Heavy single partner, 100/second for 5 seconds: 457 submission 201, 36 submission
  429, 7 submission timeouts; 44 duplicate 201, 3 duplicate 429; 444 successful
  polls, 13 poll timeouts; 49 invalid-key 401, one invalid-key timeout.
  Submission p95 12.94 seconds. Both quota rejection and overload were observed.

The 160 in-flight-job client cap bounds pressure; scheduled arrivals may queue
at the client. HTTP latency percentiles exclude that semaphore delay and are not
arrival-to-completion percentiles. Drain durations include all work. Each scenario
used only 20/10/5 seconds of arrivals, not a 30-minute steady test or minute-long
burst. Physical/Android capacity was not tested. Raw JSON records both runs and
all response classifications, including failures. A timed-out submission may
have committed: retry its original external reference and idempotency key.

Authentication and resources
----------------------------

100 offline valid verifications per key type measured legacy PBKDF2 at
133-140 ms each and new HMAC verification at 0.014-0.025 ms. PBKDF2 remains fully
verified for existing keys. The faster path requires a new securely random
256-bit credential, secret verifier pepper, constant-time comparison and explicit
rotation/revocation; this is not a benchmark-only authentication bypass.

HTTP parent/children aggregate peak CPU was 332.5% of one core in the mixed run
and 121.1% in the HMAC run. Peak HTTP RSS was 225.36/213.78 MiB respectively.
These do not include PostgreSQL, callbacks or generator memory/CPU. Sampled
maximum PostgreSQL lock waiters were 4/6. Callback fault counts each run were
59 attempts: 30 unavailable and 29 delayed accepted responses. They continued
without holding delivery transactions; separate row-lock tests prove that property.

Capacity conclusion and deployment recommendation
-------------------------------------------------

10,000/day averages 0.116 admissions/second. These short measurements demonstrate
admission far above that average under the stated workload, but do not establish
a production SLA, daily soak resilience or a 100/second burst. Retry/poll traffic,
partner distribution and contractual limits are part of sizing. A partner is
limited to 600 submissions/minute and 20/second, regardless of HTTP instance.
Financial wallet float and phone service time impose separate payout limits.

The existing one shared CPU Fly configuration was NOT benchmarked. Mixed-key
peak CPU exceeded three cores on this host: do not extrapolate the successful
10/second run to that machine. Start a controlled staging comparison with two
dedicated CPUs and 2 GiB memory for API processes, separately running callback and
reaper process groups, and a monitored PostgreSQL service. This is a measurement
plan/headroom recommendation, not verified capacity. Memory measurements alone
do not show that the old 1 GiB VM is inadequate. Retain at least one running API
machine with autostop off and keep background processes alive without requests.

Before promising burst SLAs, profile the short global financial advisory lock,
per-IP quota-row contention and DB round-trip/commit cost. Reduce measured hot
paths and establish safe lock ordering before sharding financial locks. Rotate
legacy API keys through an explicit partner migration rather than weakening their
verification. Run the same fixture in staging for at least 30 minutes at the agreed
steady rate and a full minute at the agreed burst, with DB/host metrics and callback
faults, then test recovery/restores. No production resource change or deployment
was executed during this review.
