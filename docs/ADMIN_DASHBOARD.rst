Hubaal operations dashboard
===========================

The supplied ``hubaal_admin.zip`` design is served by the existing FastAPI
application at ``/admin``. Sign in through ``/login`` with an administrator
account. No separate dashboard service or React build is required.

Source integration
------------------

The supplied HTML, colours, Manrope typography, sidebar, table layouts,
transaction drawer, mobile navigation and six views are retained in
``templates/admin.html``, ``static/admin_dashboard.css`` and ``static/admin.js``.
Business views are connected through ``static/admin_business.js``. Fonts load
from the application's existing local assets. Legacy secondary admin pages keep
their existing stylesheet.

Both archives were extracted intact into
``.simulation-runs/hubaal-admin-source`` with an SHA-256 inventory. The previous
dashboard is backed up in ``.simulation-runs/hubaal-admin-before``.
``src.zip`` contains a React redirect to ``/api/preview/admin`` and supporting
UI components; it does not implement the dashboard. That destination now
redirects authenticated administrators to ``/admin``. The public website's
React application is retained.

API connections
---------------

* Overview: ``GET /admin/api/summary`` and ``GET /admin/api/payouts``. Counts
  include uncertain outcomes and held jobs. Recent transactions show ten rows.
* Transactions: ``GET /admin/api/payouts`` with search, status and pagination;
  ``GET /admin/api/payouts/{uuid}`` provides recorded history, execution metadata
  and callback outcomes. Fifty rows load per page.
* Queue monitor: ``GET /admin/api/queue``. The supplied view shows the latest
  200 jobs; summary counts cover the full queue.
* Earnings: ``GET /admin/api/earnings``, ``/earnings/partners``,
  ``/earnings/details`` and ``/earnings/export.csv``. Period, currency, activity
  and partner filters use the financial reporting API. Fee state and sorting
  apply to the audit and CSV. Revenue comes from financial postings. Reserved
  partner money and pending fees are not recognized revenue.
* Partner funds: ``GET /admin/api/funds/partners``,
  ``GET /admin/api/funds/history/{partner_id}`` and
  ``POST /admin/api/funds/deposit``. Available, reserved and total balances use
  each partner's recorded funding currency. History lists the latest 50 funding
  records, rather than claiming to show every payout movement.
* Partnership enquiries: ``GET /admin/api/partnerships`` reads submissions
  already persisted by the public website, with bounded literal search and
  pagination. It does not send emails or create partner credentials.

Authentication and financial actions
------------------------------------

All dashboard reads and writes require the existing administrator session;
``GET /admin/api/session`` checks that access. The HttpOnly session cookie is
used on the same origin. Worker credentials and partner API keys are not
requested, embedded or stored in browser storage. Unsafe requests include the
existing CSRF token. Admin responses are marked ``no-store``.

The detail adapter selects approved fields; raw instructions, request payloads,
callback bodies and credentials are excluded. API values render as text rather
than HTML. Monetary API values remain decimal strings; display formatting does
not convert them to floating-point numbers. Pagination uses deterministic
ordering, and balance/count queries share a consistent snapshot.

Record deposit means funding already received. The operator enters the amount,
unique funding reference and evidence reference, reviews those values, then
confirms. The existing backend posts the ledger journal and enforces reference
idempotency. Retry retains the same reference. Inactive partners and accounts
without reconciled opening funding cannot use the deposit action. Direct balance
editing and direct payout-status changes remain retired.

Refresh errors retain last successful data with a stale indicator and retry.
Expired or denied sessions clear cached records and close detail dialogs; delayed
responses cannot restore data from the expired session. Polling pauses for hidden
tabs, dialogs and active filter editing.

Verification
------------

The backend regression set consists of ``tests/test_admin_dashboard.py``,
``tests/test_existing_http.py``, ``tests/test_earnings.py``,
``tests/test_public_partnerships.py`` and ``tests/test_public_site.py``. Tests
use a disposable database through ``CENTRAL_TEST_CLUSTER_URL``. Dashboard tests
cover administrator isolation, role changes, safe details, literal enquiry
search, bounded pagination, exact money values, held jobs, CSRF and duplicate
funding-reference handling.

``development_support/verify_admin_dashboard.py`` checks all six views at
1440, 1024, 768, 390 and 360 pixels. It also checks search, pagination, details,
earnings filters and CSV, funding history, deposit review and retry, errors,
session expiry, delayed responses, safe text rendering, mobile dialogs,
keyboard navigation and logout. Its funding POSTs are intercepted; no money is
written to the running demo database. Financial write tests run only in the
disposable database. The verifier is intended for the local demo account.

Screenshots and browser results are retained in
``.simulation-runs/hubaal-admin-review``. These checks establish functional
integration, not production throughput or real-device payout capacity.
