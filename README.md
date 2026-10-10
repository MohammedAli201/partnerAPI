# Partner-facing payout backend

The supplied React frontend now serves the public Hubaal website at `/`
in this same application. Build it with `cd frontend`, `npm ci`, then `npm run build`.
See [the React frontend handover](docs/REACT_FRONTEND.rst) for preview behavior,
checks, screenshots and the business details needed before publication.

Run the existing application with `uvicorn main:app`. Partners continue to use
`POST /payouts-create` and the existing status/report interfaces. The authoritative
records remain `public.partners`, `public.payouts` and `public.payout_queue`.

Install `requirements-payout.lock`, then apply the existing Alembic migration chain
as a migration owner: `python -m alembic upgrade head`. Never run this against
production before the reconciliation and restore rehearsal described in
[the review and operations guide](docs/EXISTING_BACKEND_REVIEW.rst).
An existing database without Alembic history needs an inspected baseline;
do not blindly stamp or recreate its tables.

New partners and migrated balances require independently approved opening reviews.
Execution starts globally paused. Old executor routes are permanently retired.
Registered HTTPS partner webhooks replace arbitrary per-payout destinations and
use partner-specific HMAC secrets. Browser sessions require a new login and CSRF.

Background processes must run independently:

```text
python -m payment_processes callbacks
python -m payment_processes reaper
```

The future Pi protocol is `/internal/workers/v2`; `worker_simulator.py` implements
a durable fake-worker journal. No Android or USSD automation is included.
Real-worker success remains UNKNOWN until independently reconciled.

With `CENTRAL_TEST_CLUSTER_URL` pointing to an explicitly disposable PostgreSQL
cluster, run `python -B -m pytest tests -q`. The variable name is retained by test
utilities only. `python -B benchmark_existing.py` measures the existing HTTP app
and writes [raw local measurements](docs/existing-benchmark.json).

Earlier `central/` artifacts are unused by this application. Revision 003 is a no-op reserved
in the migration history for compatibility; revision 004 hardens the existing
public records and does not migrate partners into another service. The older
CENTRAL documents describe that unused implementation, not this backend.

Run the complete four-partner/ten-phone software simulation with
`python -B -m simulation.run --profile mixed --period 120 --phones 10`.
See [the end-to-end run guide](docs/E2E_SIMULATION.rst) for prerequisites,
separate burst/spread profiles, transport boundaries and retained evidence.

The supplied Hubaal admin dashboard runs at `/admin` after administrator sign-in.
See [dashboard integration and verification](docs/ADMIN_DASHBOARD.rst) for its six
API-connected views, funding controls and browser checks.

## Offline authentication checks

Run `python -m unittest discover -s tests -p test_security.py -v` for the
standalone API-key checks, without contacting a database or payment provider.
The GitHub offline workflow runs this focused suite; the full application test
suite also needs the dependencies and disposable PostgreSQL setup above.

Keep `.env` and Python environments local. `.env.example` contains placeholders,
not deployable credentials. Removing credentials from the current source tree
does not remove them from previous Git history or rotate their values.
