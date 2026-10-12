Supplied landing source integration
===================================

The active landing page uses the owner's best/src.zip supplied on October 12,
2026. All original files and the prior frontend source are retained under
.simulation-runs/best-src-import (original/ and before.zip). import.json records
the source archive SHA-256 and file inventory.

The supplied hero, animated payout diagram, channel cards, local-support,
process, safeguards, company, integration and enquiry sections replace the
previous redesign. Unused generic UI scaffolding and the standalone App/index
bootstrap are retained with the original archive; the application continues to
use its existing router and business bootstrap, including secondary pages and
partner sign-in.

Landing-only adaptations preserve the requested League Spartan/Inter typography,
the supplied navy, teal, blue and slate palette, readable sentence-case labels, and
removal of dotted backgrounds and decorative glows. Accurate supplied provider
logos appear in the channel cards. Mobile visitors receive readable routing
labels instead of a scaled-down SVG. The supplied section structure and wording
are otherwise retained, with the implemented backend's safeguard statements.

The existing Enquiry adapter preserves the supplied form layout while using
same-origin fetch, CSRF protection, bounded fields, a persistent idempotency key,
and the actual backend receipt reference. Country and expected monthly volume
remain required by the existing enquiry record. No backend, payment processing,
or administrator changes are included in this import.

The existing Integration adapter preserves the supplied layout while showing
POST /payouts-create and the actual signed-webhook schema. Expanding or copying
an example does not submit a payment. The accessible mobile menu retains focus
handling, Escape, scrolling protection and partner sign-in. Lenis respects
reduced-motion preferences.

Validation: production build and five existing frontend adapter tests passed.
Local application and font URLs return HTTP 200. Browser screenshot review is
limited by a Windows screenshot-capture interface error in this session.

October 12 copy and spacing follow-up
------------------------------------

The owner's latest direction supersedes the earlier warm palette. The homepage
now uses the source ZIP's navy (#0B1220), teal (#14B8A6 / #0D9488), blue
(#2563EB), cool canvas (#F8FAFC), and slate text. These colour overrides are
scoped to .source-landing; other public and partner pages retain their styles.
League Spartan headings and Inter copy remain.

The hero reads "Your Somalia payout partner." Navigation and section headings
are shorter. Repeated channel labels and the status legend are removed; channel
availability remains on each card. Regulatory copy states that the Somalia
licence application is awaiting a decision and payouts are not yet live.

Safeguards now use two full-width columns of independent cards with 28px gaps
and 36/40px padding. Regulatory status and the concise four-item partner pack
occupy their own row. Channel cards also use two spacious columns, with one
shared limits/timing note. Both groups stack below 700px.

Production build and all five existing frontend tests passed for this update.
The homepage and generated assets returned HTTP 200. Screenshot review remains
limited by the Windows capture interface failure noted above.

October 12 removal and visibility follow-up
-----------------------------------------

Removed the homepage leadership profile and partner-document card at the owner's
request. The remaining licence notice fills its own row. The hero keeps the
routing diagram, with the example-transaction overlay and floating delivery
badge removed. Pointer tilt is also removed, so the diagram remains in its
layout box. The sending-partner labels have wider frames.

Dark-section headings explicitly use #F8FAFC against #0B1220, overriding the
shared heading utility's dark foreground. Integration links and the example
button use a wrapping flex group with independent spacing.

Overlap correction
------------------

The owner clarified that the demo cards should remain. Both the example payout
card and the delivered-status badge are restored. The status badge has its own
row above the routing diagram; the payout card has its own row below it. All
three remain in normal document flow with 18px gaps, so they reserve space on
desktop and mobile instead of covering routing labels. Example status cycling
is retained and respects reduced motion. The leadership and partner-document
removals and dark-heading visibility fixes remain.

Floating-card reference refinement
---------------------------------

The owner's latest screenshot guides the hero composition. The delivery badge
floats at the frame's upper right, with 52px top padding inside the frame to
keep the heading below the badge. The example payout card overlaps only the
frame's lower empty border area: 32px bottom padding and a 16px negative margin
leave 16px of clearance below the diagram. The payout card remains in document
flow so later content cannot rise under it. The four progress states share one
row on desktop and two rows on mobile, with readable labels. Original blue
inbound routes and the two-colour central mark are restored.

Payout-channel scrolling restored
--------------------------------

The owner requested the moving payout-channel strip. It is rendered again
between the hero and channel coverage. Two equal channel sets create a seamless
28-second leftward loop, with a fixed label and a pause/resume button. Hovering
over the moving channel area also pauses it. Reduced-motion visitors see one
static, wrapping set, with the duplicate and pause control hidden. The strip
retains the supplied channel badge colours.

Midnight indigo direction
------------------------

The owner's latest palette direction supersedes the ZIP palette: midnight
indigo #171C3A, warm apricot #F4B98A and ivory #F7F3EC. The hero, navigation and
footer use indigo; primary actions and selected headings use apricot. Reading
sections use ivory. Provider logos keep their supplied colours. All palette
changes remain scoped to the landing page.

The hero is composed as "Your Somalia / payout partner." at 72px, weight 700
on desktop, with one supporting sentence and one action. Section headings use
League Spartan 56px/500; body and controls use Inter. Qualified heading selectors
fix the earlier Inter override caused by the shared heading utility. The 72px
second line measures 477px including letter spacing, so the two-column hero
starts at 1200px, where each text column is 536px. Narrower screens stack the
hero and use the mobile navigation. The full-height hero constraint is removed.

The owner's comparison screenshot guides Why Hubaal: two spacious indigo cards,
apricot headings, concise ivory copy and working links to company/enquiries,
under a centred heading. Existing leadership/document removals remain.

The dev server's stale Tailwind configuration produced a stylesheet HTTP 500.
Restarting that verified workspace Vite process restored HTTP 200. The channel
strip is rendered and has a direct #payout-channels anchor. CSS inspection
confirms its loop animation, the font roles and heading weights. Main action
contrast is 9.62:1; ivory on indigo is 15.03:1; body copy on ivory is 4.91:1.
Production build and five existing frontend tests passed. Browser automation
was unavailable during this review, so visual verification is incomplete.

Reference hierarchy follow-up
-----------------------------

The owner's latest comparison screenshot guides How Hubaal works. Its heading
now spans up to 1060px instead of a narrow 720px block. A clear contact action
precedes four open columns, each with an 80px apricot circular icon, a readable
step number, a League Spartan title and concise Inter copy. Decorative connector
lines and tiny floating step-number badges are removed. Columns switch from
four to two to one at narrower widths. The original four payout steps and their
meaning remain; none of the reference site's coverage or regulatory claims is
adopted.

The refreshed production homepage and dev stylesheet/component requests return
HTTP 200. The current build includes both comparison-driven section changes.

Human onboarding, light contact form and safeguards accordion
------------------------------------------------------------

The owner supplied further onboarding and contact references, then selected
expandable rows for Confidence in every step. Safeguards now use a left heading
and action beside four accessible accordion rows, with the first open by default
and the licence notice still visible below. No separate duplicated FAQ is added.

The integration section uses a three-step onboarding accordion beside an
original transparent illustrative phone-user image. The built-in image_gen tool
created the asset; its exact prompt and provenance are in
frontend/src/assets/onboarding/provenance.json. It depicts a fictional model,
not a Hubaal employee. API examples remain expandable below, use the real schema,
and do not submit payments.

The enquiry form uses a warm light card on indigo, readable labels, clear selected
channels, real support/documentation links, and the existing backend adapter.
CSRF, idempotency, all seven field names, validation and receipt behavior remain.
No fields or data collection from the competitor's form are copied.

Production build and five frontend tests passed. Server-rendered markup checks
confirmed four linked safeguard panels, three onboarding panels, one initially
open panel per accordion, and all seven backend enquiry field names. The current
homepage, built photo, dev stylesheet and changed components return HTTP 200.
Browser visual review remains incomplete because the automation tools failed.

Payout-directory refinement
--------------------------

At the owner's request, the oversized channel-card grid is replaced by one
quiet payout directory. A midnight-indigo masthead identifies Somalia and USD
once. Uniform provider artwork, aligned channel/provider names, delivery methods
and restrained availability badges form four rows, in the original EVC Plus,
ZAAD, eDahab, Bank transfer order. The source logos and provider colours are
preserved. A common note retains registration, name matching and pilot limits.

At smaller widths each row reflows into a logo/name group and a method/status
line without horizontal scrolling. Currency remains identified in the caption
and accessible row details. Server-rendered markup checks confirm all four row,
status and currency identifiers, three testing statuses and one planned status.

About panel and lean enquiry form
---------------------------------

The latest About reference is translated into one centred indigo panel, a short
Somalia-focused statement and a three-node business / Hubaal / recipient flow.
Apricot highlights Hubaal. Company and contact facts remain in the footer rather
than repeating them in the About section. No reference-site service or licence
claims are copied.

The owner requested a leaner contact form. Its column now has a 520px maximum
width and a single-line submit action. Their subsequent request for more height
and breathing room sets 48px fields, 24px row gaps, a 112px resizable message area
and 36px vertical card padding. Field labels remain 14px and input text 16px.
The footer privacy copy is shorter; its privacy link remains. The seven backend
fields, channel selection, submit adapter and receipt handling are preserved.

The production build passed. A server-rendered probe confirmed the seven field
names, four channel choices, three message rows, privacy link and About flow.
The local homepage serves the current JavaScript and stylesheet with HTTP 200.
No enquiry was submitted. Browser visual review remains unavailable.

Spacing, natural heading wrapping and restrained actions
-------------------------------------------------------

The owner's next screenshots identify excess space between sections and repeated
contact buttons. Desktop section padding is reduced from 96px to 64px. Adjacent
ivory sections start with 24px top padding, so their combined separation is 88px
instead of 192px. Mobile uses 48px bottom and 16px adjacent top padding.

Why Hubaal uses the full heading width and has no forced line break. Its two
solid indigo cards retain readable internal padding and shorter supporting copy,
without Meet Hubaal or Talk to our team buttons. Contact actions are confined to
the navigation and hero. Repeated process, safeguards and footer enquiry links
are removed. Footer email, phone, legal details and regulatory status remain.

The payout-support heading spans the available width above one full-width solid
indigo box. Ivory primary text and muted light supporting text preserve contrast.
The outcome, case reference and agreed onboarding procedures remain visible.
Other section headings wrap naturally; mobile headings are not forced onto one
line. The enquiry form's previously requested vertical breathing room remains.

Production build and server-rendered checks pass: two enquiry links in the
default navigation/hero view, no forced heading breaks, all four payout steps,
all four safeguard panels, and the solid support panel. Browser visual review
remains unavailable.

Narrow form reference
---------------------

The owner's subsequent form screenshot is used as a composition reference.
Hubaal's form is capped at 440px, pairs name/email where space permits, and uses
full-width business, country and volume fields. Four native labelled channel
checkboxes form a two-column grid. Optional payout details use a native disclosure
that starts closed; the message field and backend payload remain available.
The submit button spans the card below the existing privacy note. Labels stay
14px, field text 16px and inputs 44px tall, rather than copying the reference's
small typography. Indigo, apricot and ivory remain Hubaal's palette.

No competitor product options, LinkedIn/phone fields or consent wording are
copied. CSRF, idempotency, required fields, error handling and receipt behavior
are preserved. Build and server-rendered markup checks pass for all seven field
names, four channel checkboxes, EVC Plus selected by default, the privacy link
and the initially closed optional message. No enquiry was submitted.


Compact coverage reference
--------------------------

The owner's next reference selects Belmoney's split copy/card composition for
payout channels. Coverage now uses a short heading and paragraph, two concise
capability points and the existing beneficiary/limits note on the left, beside
one quiet warm-white card on the right. Four compact rows retain original
provider logos, provider names and three testing / one planned statuses.
The heavy masthead, table headers, grid lines and repeated delivery column are
removed. Somalia/USD context remains visible in the copy and accessible list
label; delivery methods and per-channel currency remain accessible row details.

The card uses 22px League Spartan names and 14px provider/status text. Columns
stack below 1024px; below 480px statuses move beneath identities to give text
room. No new enquiry button or reference-site currency/coverage/licensing
claim is added. Production build and server-rendered checks passed for all four
channel/status/currency identifiers, three genuine logos and accurate statuses.
The local homepage and latest assets return HTTP 200. Browser visual review
remains unavailable.
