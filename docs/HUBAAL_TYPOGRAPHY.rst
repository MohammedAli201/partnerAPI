Typography reference: bel.money
===============================

The reference homepage's CSS was inspected directly. Its default text uses
Inter 400, clamp(16px,2vw,18px), line height 1.5 and zero tracking. Its headings
use League Spartan: h1 700, clamp(32px,6vw,72px), line height 0.9, tracking
-0.01em; h2 500, clamp(32px,6vw,58px), line height 0.9, tracking -0.01em.
Its additional feature blocks use Roboto for supporting copy and Roboto Mono
for small labels. The typography stylesheet applies these roles to Hubaal.
Compact cards follow its 20-24px heading pattern, not its large page headings.

Fonts are self-hosted from Google Fonts, including Latin and Latin Extended,
with font-display swap. OFL licences and exact font origins/checksums are in
static/hubaal/fonts. Existing typography assets remain available to unrelated
pages. The reference's text, logos, company claims and regulatory details were
not copied. Hubaal's layout and motion implementations remain intact.

Reference: https://bel.money/
Implementation: frontend/src/reference-typography.css
