Supplied React frontend integration
===================================

Current source
--------------

The active website uses all 21 files supplied from
``C:/Users/Mohamed/Documents/partner frontend/f0/src``: four application/style
files and seventeen components. This update supersedes ``fron/frontend.zip``.
The originals, source hashes and final integration diffs are retained in
``.simulation-runs/hubaal-f0-source``. The previous frontend is backed up at
``.simulation-runs/hubaal-before-f0.zip``. None of the supplied files is omitted.

Following the user's request to remove repeated landing-page information, the
homepage now contains Hero, StatsBand, Channels, PartnerBand, HowItWorks,
PartnerApi, About, Faq and PartnershipForm, followed by Footer. The moving
burgundy service strip is restored at the user's request. Its latest supplied
wording is ``USD payouts · Mobile wallets · Bank accounts · Cash pickup · Based
in Mogadishu``, replacing the earlier numeric metrics and response-time label.
The payout-model panel and duplicate
coverage panel are no longer rendered on the homepage.
Their supplied component files remain available; the detailed coverage component
is still used on the separate partner page. Existing secondary routes remain.

Current copy review (2026-10-10)
-------------------------------

Frontend company-site cleanup (before publication)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Approved homepage copy, supplied logos, responsive font sizes, colours and the
slim moving service strip are preserved. Main navigation follows section order.
Secondary company pages share the 1200px content width with the navigation and
footer. About uses the approved local-team section; English help reuses the
three current partner questions. Contact provides working company email links
and the partnership enquiry form rather than an unsent downloadable support
draft. The integration guide also links to that working enquiry form.

Privacy copy no longer contains an unfinished retention instruction or claims
an analytics tool that the frontend does not load. Policy contact addresses are
clickable. The enquiry form provides autocomplete, a privacy link, visible
keyboard focus, a labelled sending state and recoverable errors. Inputs are
temporarily disabled while a submission is pending. FAQ and onboarding controls
identify their answer panels for assistive technology.

Page titles and sharing metadata use company wording. The JavaScript-disabled
fallback supplies a partnership email and the service-status notice. Preview
indexing restrictions remain; this update does not publish or activate payouts.
No backend API, payment processing or dashboard changes are included.

Validation: production build and five frontend tests passed. The existing
browser review passed at 360, 390, 768, 1024 and 1440px. Company route metadata,
layouts, help search, pending enquiry controls and error recovery also passed
at 390 and 1440px, including a JavaScript-disabled home check. Enquiry responses
were mocked; no live enquiries or financial transactions were submitted.
Screenshots and the scoped report are in
``.simulation-runs/hubaal-company-cleanup``.

Approved homepage wording
~~~~~~~~~~~~~~~~~~~~~~~~

The latest user-supplied hero reads ``Your payout partner in Somalia.`` and
describes USD payouts for overseas remittance companies and payment businesses.
It also states ``Partnership enquiries are open. Payout services are not yet
live.`` The wordmark
subtitle is ``PAYOUT PARTNER`` and the public brand is ``Hubaal``. The address
remains Mogadishu, Somalia; no overseas branch locations are claimed.

Receiving options appear once in the homepage channel section: EVC Plus, ZAAD,
eDahab, Salaam Bank, Premier Bank and cash pickup, with USD recipient currency.
The cleaner Why Hubaal layout uses four small icons and distinct explanations
of integration, local delivery, outcome reporting and reconciliation, using
the user's latest supplied wording.
It does not adopt unverified settlement-speed, funding, compliance or SLA claims
from the reference screenshot.

Commercial onboarding steps appear in one section. Repeated About feature
points, form onboarding instructions and the footer sales CTA are removed.
Three FAQ items address launch availability, the intended business audience
and whether an enquiry establishes a partnership. The integration panel shows
an explicitly labelled example instruction with ``HB-EXAMPLE-001``,
``USD 100.00`` and ``Instruction accepted. Payout pending.``, rather than payment-card
artwork, and links to the working integration guide.

The dark footer displays the user-supplied disclosure from public business
configuration: ``Hubaal is in the process of obtaining approval. Our payout
service is not live yet.`` Legal routes also include this footer. Launch mode
remains preview. Existing ``#coverage`` bookmarks navigate to the consolidated
channel section; navigation links target the remaining sections directly.

Production build, five frontend adapter tests and twenty existing public-site
and enquiry tests passed. Database checks used a separate disposable database.
``development_support/verify_f0_frontend.py`` now checks the nine-section
composition, specified responsive Manrope sizes, three FAQs, mobile keyboard
navigation, legacy links, ten secondary routes and mocked enquiry recovery at
360, 390, 768, 1024 and 1440px. Screenshots and the current report are in
``.simulation-runs/hubaal-copy-review``. No browser errors, failed asset requests,
external requests or horizontal overflow were recorded. Live provider delivery
was not tested or activated. The following sections retain earlier implementation
records; this current review supersedes their homepage counts and descriptions.

FAQ typography follow-up
------------------------

The FAQ was already Manrope, but its 700 heading weight and 1.1 line height
differed from the other display headings. It now explicitly uses Manrope 800,
32/40/48px at the existing breakpoints, 1.2 line height and the same letter
spacing as Why Hubaal. The section label uses the shared burgundy eyebrow.
Heading spacing is 28px; accordion gaps are 16px, with 24px vertical button
padding. Questions remain 15/16px and answers 15px, with more readable line
spacing. The latest supplied three-question FAQ replaces the preceding four
questions. The approval disclosure remains.

The marquee uses a slim 42/44px strip, 14/15px Manrope phrases and a slower
50-second linear loop with GPU-friendly transforms. It pauses on hover. Reduced-motion
visitors see all service labels in a static wrapping row rather than clipped
off-screen content. The browser review checks animation movement, hover pause,
the static presentation, FAQ font metrics and all existing interactions.

The final build and five-width browser review passed after the latest copy
update. ``.simulation-runs/hubaal-copy-review/supplied-copy.json`` records
desktop/mobile checks against the supplied headings, onboarding bodies, FAQ
answers, strip phrases, primary navigation destinations and example fields.

Typography and build
--------------------

The source typography classes are retained outside the subsequently updated
About section. The approved fonts remain
self-hosted Manrope and Space Mono, with the stacks ``Manrope, sans-serif`` and
``Space Mono, monospace``. The source supplies no HTML font loader, package
manifest or Tailwind configuration; the existing approved theme supplies them.

Hero text is 40px below 640px, 52px from 640px and 68px from 1024px, weight 800,
line-height 1.1 and tracking -0.02em. Ordinary section headings retain their
individual source sizes and line heights; the larger payout/API/footer display
headings are 32px/44px/52px. Form fields and submit text remain 16px; labels are
13px/600. Footer body and links remain 15px; copyright/location text is 13px.
The dark hero, payout model, API section, enquiry panel and full footer remain.
The About section now follows the user-supplied image reference described below.
Burgundy buttons and brass accents remain.

The palette remains white ``#FFFFFF``, surface ``#F5F6F7``, navy ``#16202F``,
burgundy ``#7C2434``, burgundy glow ``#96303F``, brass ``#C9A45C``, cream
``#EFE9DC``, text ``#1B2432``, dim text ``#58606B`` and muted text ``#8A94A3``.
The source's missing mist, line and dark-hover tokens use ``#EEF0F2``,
``#E2E6EA`` and ``#64202E``. The new marquee uses a continuous 32-second loop,
pauses on hover and stops for reduced-motion preferences.

Tailwind is pinned to 3.4.19, matching the supplied ``@tailwind`` directives and
avoiding competing Tailwind 4/archived utility rules. PostCSS uses Tailwind and
autoprefixer. The previous ``archive-production.css`` file remains available but
is no longer imported. Existing Vite JSX support and Docker build remain.

Retained company and functional requirements
-------------------------------------------

``frontend/src/channels.js`` supplies five channels for the cards and interactive
coverage filters: EVC Plus, ZAAD, eDahab, Salaam Bank and Premier Bank. SAHAL is
removed from cards, coverage and FAQ. The channel statistic reads 5. All coverage
cards show USD; source demonstration amounts retain their USD labels.
The enquiry dropdown remains All channels, Wallets only, Banks only and
Wallets + banks, without cash pickup.

Four user-supplied logos remain bundled with their original pixels and colours.
Proportional white frames are 80x48px on small screens and 96x56px from 640px;
logo and text stack below 640px to fit the source's two-column grid. eDahab's
extra white margin is clipped in CSS, preserving its artwork. ZAAD uses the
neutral wallet icon. The source's workflow photograph uses its existing local
copy and accurate alt text, ?Woman seated at a market stall?. The supplied
Partner API visual has a discreet illustrative-data label.

The supplied FAQ and onboarding accordions, coverage filters and marquee are
active. Navigation switches to the supplied mobile drawer below
1024px so desktop controls fit. The drawer traps keyboard focus, closes with
Escape or desktop resizing, restores scrolling/focus and does not block its
section links. Header/footer hashes work from secondary pages; smooth scrolling
aligns targets below the fixed header and preserves browser history. The old
``/#integration`` URL maps to the current Why Hubaal section.

The form submits to same-origin ``POST /api/partnerships``. It requires
``received=true`` and a reference before displaying success, after the backend
commits the enquiry. Existing UUID idempotency keys, field bounds, validation,
database-backed IP limits and Origin/CSRF checks remain. Failure keeps entered
fields; success focuses and scrolls to the receipt. The source's New enquiry
button clears fields, reference and submission key. Administrators read stored
enquiries at ``/admin/partnerships`` through the authenticated, escaped and
paginated inbox. Migration ``20261009_000008`` remains in use.

This form stores enquiries; it does not send notification emails or replies.
Enquiries are separate from balances, payout instructions and ledgers. Backend
workers, providers, financial records, authentication and earnings remain
unchanged. Existing preview/noindex configuration and secondary-route draft
tools remain. The legal wording is retained from the source; no analytics or
retention job is activated by this frontend integration. These configuration
facts are documented here, outside the public website.

Build and validation
--------------------

The local website is ``http://127.0.0.1:8000/``. Rebuild before refreshing::

    cd frontend
    npm ci
    npm run build

Vite writes hashed assets and its manifest to ``static/hubaal-react``. FastAPI
reads that manifest when rendering the public site. Fonts resolve through
FastAPI at runtime. This change does not deploy or rebuild a running container.

The production build and five existing frontend tests passed.
``development_support/compare_f0_styles.py`` compares 1,390 element styles with
an isolated build of the untouched supplied components at 360, 390, 768, 1024
and 1440px. Shared font family, size, weight, leading, tracking, colours, padding,
margins, borders and gaps match. The documented company-logo and navigation
adaptations have their source differences recorded separately. The isolated
reference is never served by the application.

``development_support/verify_f0_frontend.py`` verifies all eleven sections, full
footer, five channels, USD coverage, loaded logos/photograph, filters, the reference About section, all six FAQs, onboarding accordions, keyboard menu, marquee, ten secondary
public routes, mobile hash scrolling and browser history. It checks overflow,
JavaScript errors, failed responses and external requests at those five widths.
The ``--store-enquiries`` run stores two synthetic local enquiries, verifies
failure recovery and reset, then confirms both through the authenticated admin
inbox. Subsequent runs default to mocked receipts to avoid storing repeats.
Screenshots and reports are in ``.simulation-runs/hubaal-f0-review``.
These checks do not test live receiving networks. The unchanged backend
previously passed 18 dedicated public-site/enquiry tests.

The source inventory and final file diffs are in
``.simulation-runs/hubaal-f0-source/integration.json``. Earlier new2, new3,
copy-trim and fron reports are historical.

About section image update
--------------------------

The user's subsequent ``Hubaal_ Local Presence, Clear Payouts.png`` replaces
only the f0 About section. ``components/About.jsx`` now renders the supplied
headline ?Local presence. Clear payout outcomes.?, both service paragraphs,
Mogadishu operations card, working partners@hubaal.so email link, partnership
CTA and all three numbered service points. The previous About tabs are removed.
``components/About.css`` scopes the new layout and typography to this section.
The reference is implemented as live HTML/CSS, including decorative SVG arcs;
it is not embedded as a screenshot.

The initial image adaptation used a wider 1440px container and larger display
type. The subsequent typography specification below supersedes those sizes
and aligns the container with the other sections. The main columns begin at 1024px; the service
points form three columns from 640px. Smaller screens stack the contact card
and service points without overflow. Other sections and the enquiry backend
remain unchanged.

The production build passed. Isolated browser review checked the exact copy,
contact and CTA destinations, remaining eleven homepage sections and full
footer, reduced/normal-motion scrolling, and layout at 360, 390, 768, 1024,
1440 and 1536px. The final desktop headline has two lines. Reference, previous
component, screenshots and verification results are retained in
``.simulation-runs/hubaal-about-reference``. The f0 typography comparison now
excludes About, because the image supersedes that component's earlier design.


Responsive typography and FAQ alignment
---------------------------------------

The latest user specification sets Manrope (400 through 800) for general text
and Space Mono for technical accents only. Existing locally hosted fonts and
Tailwind font tokens already provide both families. General labels, branding
and secondary-page labels now use Manrope. Numbered About service points,
payout references and timeline times use Space Mono.

Breakpoints remain 640px for tablet and 1024px for desktop. Heading sizes in
mobile/tablet/desktop CSS pixels are:

* Hero: 40 / 52 / 68, weight 800.
* Channels, onboarding and enquiry form: 28 / 38 / 44.
* Payout model, partner API and footer CTA: 32 / 44 / 52, weight 800.
* Why Hubaal and FAQ: 32 / 40 / 48.
* Coverage: 28 / 38 / 38.
* About statement, including its burgundy line: 32 / 40 / 52, weight 800.

About retains the supplied image composition, copy, navy operations card and
three service points. Its main story is 18 / 20 / 20px, labels 11 / 12 / 12px,
and CTA 16px. Its container now matches the site's 1200px width and 20 / 32px
side padding. The prior oversized, viewport-dependent display sizes are removed.

FAQ uses two top-aligned desktop columns without a sticky introduction. A
single gap rule spaces the accordion cards; questions are 15 / 16 / 16px and
answers 15px. Help text and its email link share one wrapping text block next
to the icon, avoiding anonymous flex items and narrow-screen misalignment.

The earlier f0 style-comparison report is a historical source baseline; this
user specification takes precedence over it. Current browser typography
measurements, alignment results and About/FAQ screenshots are retained in
``.simulation-runs/hubaal-typography``. The complete existing frontend review
continues to check all sections, full footer, navigation, accordions, filters
and mocked enquiry recovery without generating more stored enquiries.

Verification: production build passed. All 41 computed-size/family checks
passed at 360, 390, 640, 768, 1024 and 1440px, including heading weights,
technical-only mono text and desktop FAQ alignment before/after scrolling.
The complete five-width frontend review also passed, including ten secondary
routes, all accordions, full footer, mobile keyboard/navigation and mocked
enquiry failure/recovery. No browser errors, failed asset requests or
horizontal overflow were reported.


Updated receiving-channel logos
-------------------------------

All five latest user-supplied PNG files replace the earlier channel artwork:
EVC Plus, ZAAD, eDahab, Salaam Bank and Premier Bank. Their original bytes
are copied into ``src/assets/channel-logos``; provenance records their source
paths, hashes and natural dimensions. ZAAD now displays its supplied logo
in place of the neutral icon.

``ChannelLogo.jsx`` and its scoped CSS fit the visible artwork inside equal
logo areas, accounting for the PNGs' transparent outer margins. The original
images are not recoloured, stretched or rewritten. Card labels remain Manrope
at 16px on mobile and 18px from 640px; types remain 12px. Cards stack logos
and labels through tablet widths, then place them side by side from 1280px
so the grid does not compress or overlap brand names. At tablet/desktop
widths, three wallet cards occupy the first row and two bank cards fill
the second row. On mobile the final card spans both columns. This removes
the empty trailing grid cell without changing the five-channel list.

The five receiving channels and USD policy remain as configured. Updated
logo screenshots and browser measurements are retained in
``.simulation-runs/hubaal-logo-review``.

The final production build passed. Browser review at 360, 390, 768, 1024,
1280 and 1440px confirmed all five PNGs load, original hashes match, labels
retain the specified Manrope sizes, and logo frames/text remain inside cards
without horizontal page overflow or browser/asset errors.


Standalone logo replacements
----------------------------

The subsequent supplied standalone PNG artwork replaces the boxed Salaam
Bank, ZAAD and Premier Bank variants. Their original files are copied
unchanged, with updated dimensions and CSS display frames in ``channels.js``
and source hashes in ``channel-logos/provenance.json``. The existing five-card
layout, channel names, Manrope sizes and EVC Plus/eDahab assets are retained.
Previous artwork and configuration are backed up in
``.simulation-runs/hubaal-unboxed-logos-before``.

The production build and six-width logo review passed for the standalone
versions. Screenshots, original-file hash checks and card-fit measurements
are in ``.simulation-runs/hubaal-logo-review``.
