Hubaal website copy implementation
=================================

Latest source update
--------------------

The current landing-page consolidation and approval disclosure are documented
in the ``Current copy review (2026-10-10)`` section of ``docs/REACT_FRONTEND.rst``.
Hubaal is positioned as the local Somalia payout agent for remittance businesses
worldwide. The homepage has nine sections, including the restored moving
burgundy strip with the latest five supporting service phrases, and a dark footer stating
that approval is in progress and the payout service is not live yet.

The user subsequently supplied ``new2/src.zip`` and asked for the complete code
including the footer. The latest ``f0/src`` files now supply the complete homepage
composition, typography and legal-page copy; prior logo, channel-removal and
enquiry requirements remain.
The implementation below records the earlier copy-only update and is historical.
The active implementation is documented in ``docs/REACT_FRONTEND.rst``. In
particular, the current homepage enquiry form stores submissions through
``/api/partnerships`` and administrators read them at ``/admin/partnerships``;
it is no longer the earlier downloadable-draft homepage form.

The public copy states the service supplied by the user: Hubaal Express delivers
USD payouts in Somalia for international remittance companies and payment
businesses. Mobile-wallet channels are EVC Plus, ZAAD, SAHAL and eDahab. Bank
channels are Salaam Bank and Premier Bank. The About section and partner
operations card use the user's exact English wording. Somali copy is updated
alongside it and still requires native-speaker review before live language approval.

The existing ivory, burgundy, navy and brass design, fonts, photographs, section
widths, responsive cards and navigation behaviour are retained. A shared
PartnerOnboarding component presents the three requested steps on the homepage
and partner page. Pricing, funding arrangements and operational contacts appear
together there. Navigation and footer links reach the new onboarding anchor.

Public implementation banners, unfinished-policy instructions and repeated
onboarding qualifications are removed. The hero, service cards, receiving guide,
partner page, help, tracking, contact and footer use direct service descriptions.
All eight receiving rows show USD; demonstration amounts use USD 100.00. Named
payout examples remain labelled as examples and do not expose real partner data.

Working destinations
--------------------

The operations card's primary link goes to ``/?lang=en#partner-form`` (or its
Somali equivalent). It opens the existing partnership enquiry flow. The secondary
link goes to ``/login`` for authenticated partner access. No invented email address,
telephone number, support schedule or response deadline is introduced.

The enquiry tools remain downloadable-draft tools. The public form states that it
does not send an enquiry; server responses continue to enforce ``sent=false`` and
``stored=false``. Validation, review/download, failure recovery and keyboard focus
behaviour are retained. An actual enquiry receiver is a separate backend task.

Technical configuration
-----------------------

``public_site/business.py`` stores the user-supplied currency, country and six
network names. This is public company configuration; changing it does not provision
a provider integration or execute a payout. Payout authentication, partner
isolation, worker execution, ledger accounting and callbacks are unchanged.

The internal launch mode remains ``preview`` with noindex controls and synthetic
tracking examples. It is no longer presented as a public-site implementation
warning. Live launch configuration still requires the actual legal entity,
licensing disclosure, domain, contacts, support hours/time zone and reviewed
privacy, terms and complaints content. Generic website-use information does not
replace a reviewed full legal policy. Receiving-network descriptions here are
supplied company facts, not evidence of a newly tested live provider adapter.

Partner credentials and callback signing secrets remain private, server-side
configuration. Public bootstrap data must contain no API keys, balances, payout
records or application secrets. A future enquiry receiver needs explicit delivery,
retention and failure handling. Public recipient tracking still requires
verification; the current public tracking panel uses synthetic scenarios.

The local HTTP server was restarted separately from PostgreSQL to reload the
shared bilingual copy. No financial data migration or change to the existing
10,000-transaction dataset is part of this copy update.

Validation
----------

Production build and five frontend adapter/validation tests passed. Five existing
public-site tests passed against a separate disposable database. Forty-seven
responsive public-route renders and three real-browser interaction journeys passed.
Screenshots and reports are in ``.simulation-runs/hubaal-new-design`` and
``.simulation-runs/hubaal-react-preview``. The final copy review is recorded in
``.simulation-runs/hubaal-copy-review/report.json``. These are scoped checks, not
a live provider-delivery test or full accessibility certification.
