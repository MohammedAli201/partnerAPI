Hubaal Express public website
============================

The supplied React frontend supersedes this initial Jinja preview. Current source,
run instructions and validation are documented in ``REACT_FRONTEND.rst``. The
notes below describe the earlier implementation retained as a build-missing fallback.

The existing FastAPI application now serves the public Hubaal website at ``/``.
It uses Jinja templates, local CSS and small vanilla JavaScript modules. Existing
partner authentication, payout APIs, admin screens and earnings remain in the same
``main:app`` application. No new database migration is needed for this website.

Preview and service scope
-------------------------

The configured service is partner payouts, with Somalia as the initial design
focus. No retail payment or quote journey is enabled. No live receiving network,
licence, company address, contact destination or commercial partnership has been
invented. Submission, status, notifications and reconciliation are presented as
sandbox capabilities supported by the existing backend.

The website is explicitly a preview. Pages carry ``noindex`` metadata and response
headers; robots excludes all routes and the preview sitemap contains no URLs.
Policies are labelled draft layouts. Missing contact and social links are hidden.

Routes include home, receive, partners, about, help, contact, track, privacy,
terms, complaints and ``/partners/integration``. Receiving guidance and partnership
enquiries have separate journeys. The existing authenticated portal is ``/login``.

English is complete. Somali has matching structured resources and actually changes
the rendered content, including forms and statuses. Somali remains flagged for
human review and is available only in preview until that flag is approved.

Forms and tracking
------------------

Partner and support forms validate on the client and server. They offer an editable
review dialog and a local text download. Responses explicitly say ``sent=false``
and ``stored=false``: no email, CRM submission, database retention or payment is
created. Form content is returned to the same browser, with ``Cache-Control:
no-store``. No enquiry contents are sent to analytics. These are preview tools,
not a connected enquiry service.

Tracking directs authorised partners to the existing portal. It does not provide
a public payout-reference lookup. Separately labelled synthetic fixtures show
processing, confirmed delivery, failure and action required. ``UNKNOWN`` always
requires review and never becomes a delivered outcome. The client prevents stale
example responses from replacing the current selection.

Main implementation files
-------------------------

* ``main.py``: public root and router registration alongside existing functionality.
* ``public_site/business.py``: frozen Pydantic business configuration and live checks.
* ``public_site/translations.py``: English/Somali copy and human review metadata.
* ``public_site/fixtures.py``: synthetic status fixtures only.
* ``public_site/adapters.py``: bounded draft validation and honest preview response.
* ``public_site/routes.py``: pages, metadata, robots, sitemap and preview endpoints.
* ``templates/public/``: header, footer, reusable sections, pages, forms and dialog.
* ``static/hubaal/``: brand assets, design tokens, responsive layouts and interactions.
* ``tests/test_public_site.py`` and ``tests/public_site_core.test.cjs``: API/content
  boundaries, field validation, locale behavior and stale response handling.
* ``development_support/`` public preview utilities: isolated rendering and browser
  interaction verification. They never connect to a user's browser profile.

The temporary H symbol, wordmark and courtyard illustration are original SVGs.
Local Inter and Manrope variable fonts contain only the Latin resources needed
for English and Somali. Their OFL licences are included beside the font files.
There are no third-party image, analytics or animation dependencies. The homepage
story image is lazy loaded; image dimensions are declared and font display is swap.

Preview instructions
--------------------

Use the project's existing environment and database setup, then run::

    uvicorn main:app --host 127.0.0.1 --port 8000

For the reviewed local demonstration, the server is running at
``http://127.0.0.1:8000/`` against the owned 10,000-transfer simulation database.
The current admin remains at ``/admin``. That demonstration launcher lives in the
ignored ``.simulation-runs/dashboard_local.py`` and is specific to this machine;
it is not a deployment entry point. Production setup remains documented in README.

Checks performed
----------------

* 16 Python tests passed across public website, existing HTTP/auth boundaries and
  earnings. Tests use disposable databases on the explicitly selected test cluster.
  The running demo also passed admin login, admin-page and earnings-API checks;
  its 10,000 payouts, four partners and 9,214 ledger journals remained unchanged.
* Five Node tests passed: partner/support validation, stale results and errors,
  and locale URLs preserving route, query and anchor.
* Node syntax checks, Python source parsing, public Jinja template compilation and
  whitespace checks completed. This Jinja project has no frontend build, TypeScript
  configuration or configured frontend lint task.
* All 10 requested public routes were captured at 360, 390, 768, 1280 and 1440 CSS
  pixels. Screenshots and DOM copies are in ignored
  ``.simulation-runs/hubaal-preview/``. Desktop and mobile home, receiving, partner
  form, help, tracking, Somali layouts and lower home sections were visually inspected.
* 65 isolated browser artifact cases passed across all public pages, the integration
  guide and two Somali pages at the five widths. These exercise the real frontend
  code with synthetic API stubs: overflow, landmarks, labels, image alternatives,
  menu focus wrapping, Escape, scroll lock, searchable FAQs, form failure and UNKNOWN.
  Results: ``docs/hubaal-browser-validation.json``.
* Three additional real localhost browser journeys passed at 390 and 1440 CSS pixels
  and 720 CSS pixels with 2x device density. They use native keyboard events and the
  actual preview APIs for validation, escaped review, local download, language
  navigation preserving anchors, and UNKNOWN. A deliberately injected 503 checks
  editable failure recovery. Results: ``docs/hubaal-real-browser-validation.json``.
* The 720 CSS pixel / 2x density case checks the reflow equivalent of a 1440px desktop
  at 200% zoom; a physical browser zoom control was not tested.
* Seven main text/control colour pairs passed their checked contrast thresholds.
  Ratios are in ``docs/hubaal-contrast-checks.json``. Visible focus, reduced motion,
  live form announcements and non-colour-only statuses are implemented. This is
  implementation verification, not a formal WCAG certification or full screen-reader
  audit.

Re-run focused checks::

    python -B -m pytest tests/test_public_site.py tests/test_earnings.py tests/test_existing_http.py -q
    node --test tests/public_site_core.test.cjs
    node --check static/hubaal/core.js
    node --check static/hubaal/site.js

For browser utilities, install Playwright as a development-only tool and provide
an isolated Chromium executable (not a user profile)::

    python development_support/render_public_preview.py --chromium PATH_TO_CHROMIUM
    python development_support/check_public_browser.py --chromium PATH_TO_CHROMIUM
    python development_support/verify_public_interactions.py --chromium PATH_TO_CHROMIUM

Business configuration checklist before publication
--------------------------------------------------

Populate and review ``BUSINESS`` in ``public_site/business.py`` with:

* Exact approved legal entity, public website URL and licensing disclosure.
* Support email, phone, optional WhatsApp, address, hours and time zone.
* Actual receiving countries, network/method combinations, required details and
  restrictions; distinguish receiving networks from contracted commercial partners.
* Approved settlement currencies, fees/tariffs, limits and supported delivery
  estimates. Do not substitute the simulator's fees or timing for an approved offer.
* Any verified sending coverage and retail journey, if that becomes a separate
  supported service. Retail activation is currently rejected until its authoritative
  quote and payment adapters are implemented and tested.
* Approved privacy, terms and complaints text, and reviewed Somali copy.
* Production portal/API documentation destinations and an agreed partner onboarding
  process. The existing portal requires partner authentication and account scoping.
* A connected enquiry receiver with delivery, retention, consent, abuse controls and
  genuine submission-success/error states. A configured URL alone does not implement
  this adapter. Until then, keep the preview forms or use an approved direct contact.
* Any recipient tracking integration with backend-issued verification. Do not enable
  reference-only access to recipient information or account data.

Do not switch the launch flag merely to remove the preview banner. Live configuration
rejects missing legal, contact, coverage and policy information, but the corresponding
approved content and adapters must also be reflected in the pages and verified before
publication. The preview tools are unavailable outside preview mode.
