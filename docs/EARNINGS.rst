Fee and earnings reporting
=========================

Policy and existing accounting
------------------------------

Before this feature, admission already saved the exact configured fixed fee in
``payout_reservations`` and held principal plus fee against partner prefunding.
Verified success captured that liability and posted the fee to the separate
FEES ledger account in the same transaction as payout status/history/outbox.
Definitive nonpayment released the reservation. UNKNOWN retained the hold;
webhook delivery did not recognize revenue. This behavior is preserved.

Money uses integer minor units or Decimal; USD, EUR and GBP have scale two.
Deposits are liabilities, not revenue. Available/reserved partner balances
never include the service's earned revenue. Pending fees are the fee breakdown
of existing ACTIVE reservations, not an additional reserve.

Admission now saves an immutable fee snapshot with payout/partner, amount,
currency, fixed-price calculation components, policy version, acceptance time
and activity classification. Set ``FEE_POLICY_VERSION`` when changing pricing
agreements; default ``fixed-success-v1``. Changing PARTNER_FEE does not change
old snapshots or old ledger recognition. Unique payout financial business
keys and the existing atomic success transaction prevent duplicate earning.

Reports use FEES entries in PAYOUT journals for recognition and linked
FEE_REVERSAL journals for reversals. They never recompute fees using current
configuration. Net = recognized fees posted in period - reversals posted in
period. Pending is the current snapshot across all admission dates. Lifetime
audit amounts are clearly distinguished from period amounts. CSV includes
period_gross, period_reversals, period_net and pending_fee for reconciliation.
Filters and CSV order/state filtering are shared with the paginated detail API.

Reversals
---------

POST ``/admin/api/earnings/reversals/propose`` takes payout_id, positive
integer amount_minor, unique business_reference, reason and evidence_ref.
POST ``/admin/api/earnings/reversals/{review_id}/approve`` requires a different
active administrator. Both use the existing browser session/CSRF protection.
Repeated proposals must match; repeated approvals return the original journal.
Approval rechecks the unreversed recognized amount under the financial lock.
Partial and full reversals debit fee revenue and credit the original partner's
prefunded liability; they do not change payout principal or successful status.
Each journal links to its original recognition. Approved review instructions,
snapshots and ledger history cannot be edited or deleted. Database deferred
guards verify recognition against snapshots and reversals against approvals.
The fee audit exposes reversal reason, posting time and original ledger link.
There is no automatic fee reversal based on callback failures.

Viewing reports
---------------

Open ``/admin/earnings``; navigation also links from the transaction dashboard
and Partner Funds screen. Live is the default activity. Select Simulation /
test to see the four test partners. Select one currency: different currencies
are never added together. Partner rows open the partner fee audit. The funds
screen's compact earned-fees column has explicit period/currency/activity
selectors and does not alter partner balances.

``REPORTING_TIMEZONE`` is an IANA timezone, default UTC. Inclusive date labels
map to local midnight boundaries converted to UTC; DST days may have 23 or
25 hours. All stored financial timestamps are UTC timestamptz. Reversals are
dated by their posting, including when the original payout was in a prior
month. The page shows reporting timezone, scope and last refresh time.

Admin-only endpoints:

* GET ``/admin/api/earnings``: summary, first 100 partners, daily trend.
* GET ``/admin/api/earnings/partners``: server-side partner pagination.
* GET ``/admin/api/earnings/details``: paginated/sorted/state-filtered audit.
* GET ``/admin/api/earnings/export.csv``: streaming audit, 200-row DB pages.

Common filters: preset=today|7days|month|custom, start/end ISO dates for custom,
partner_id, currency=USD|EUR|GBP, activity=live|simulation|unclassified.
Detail limit is at most 200; offset and supported sort keys are validated.
Reports aggregate in PostgreSQL; detail pagination happens before constructing
event JSON for the normal admission/fee sorts. Reporting uses posting/payout
indexes and no cached summaries. Summary and export use repeatable-read
transactions. CSV protects spreadsheet formula injection in text fields.
Internal fee reports are unavailable to partner-role sessions and partner API
keys. Execution costs are not recorded in the existing financial ledger;
contribution/profit is omitted. Revenue recognition deducts partner prefunding,
but bank collection/settlement is not modeled by this report.

Historical evidence and deployment
----------------------------------

Apply Alembic revisions 000006 and 000007 before starting this code. Startup
requires fee tables/view and guards. Migration copies original saved fee
reservations only when exact, nonnegative and in a supported currency; it does
not create fee-recognition journals. Historical policy/components unavailable
from the old data are labeled ``legacy-success-v1``/historical-snapshot.
Successful positive-fee records without matching recognition evidence are
flagged RECONCILIATION_REQUIRED; missing snapshots are also reported as gaps.
No amounts are inferred from balance differences or current fee prices.

Historical activity uses the dedicated simulation database marker or recorded
simulator worker evidence. Real worker evidence classifies live history;
records without this evidence are unclassified and excluded from live totals.
Future production admissions classify live, other environments simulation.
Unclassified historical activity needs a reviewed classification migration,
not an editable UI switch. Deployments must set ENVIRONMENT correctly; existing
production guards prohibit software simulator confirmations.

For the retained 10,000-payout simulation, all 10,000 fee snapshots have
supported reservation evidence, all 9,200 positive fee recognitions reconcile
to FEES entries, and the FEES account balance is 552000 USD minor units:

* Gross and net: USD 5520.00.
* Reversals: USD 0.00.
* Pending: USD 180.00 for 300 unresolved outcomes.
* Failed: 500 payouts; their fees are released, not earned.
* Live revenue: USD 0.00; these transactions are simulation activity.

No production database was migrated or modified during local validation.

Validation
----------

The full regression run passed 83 tests. After the final reporting and policy
snapshot refinements, all seven focused fee tests passed, including two funded
partners in two currencies, DST boundaries, prior-month recognition/current-
month reversal, partial/full reversals and rejected unapproved postings.
The existing simulation's actual HTTP CSV export contained 10,000 records and
reconciled all period recognition/reversal/net and current pending columns;
the measured export took 3.0 seconds on this local machine. Admin HTML and
report/detail APIs returned HTTP 200; anonymous and partner-role requests to
internal reports/export were rejected.

Desktop and mobile previews were rendered and visually inspected using the
installed headless Chromium shell. ``development_support/render_earnings_preview.py``
creates offline render artifacts from authenticated, read-only localhost API
snapshots and the actual page/CSS/JavaScript. It uses an isolated temporary
profile, no user's browser profile, and a mock fetch only within the offline
artifact. It does not replace backend integration tests. Set
EARNINGS_PREVIEW_PASSWORD, pass --chromium pointing to the installed headless
shell, and optionally --base-url/--output. Artifacts remain in the ignored
``.simulation-runs/earnings-preview`` directory.
