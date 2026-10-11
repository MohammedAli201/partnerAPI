Automatic EVC phone execution
=============================

Version 1.2 connects the existing payout admission, durable queue, phone claim,
authorization and result APIs to a serial Android foreground USSD worker.
No backend or chat PIN is used: the EVC PIN remains in the encrypted local vault.

New EVC/Hormuud payouts in explicitly enabled EVC mode bind the beneficiary name,
canonical +252 mobile and exact USD amount in version 2 instructions. Only these
new server-marked payouts are eligible; previous SMS and simulator payouts are
excluded. The modem command removes only +252: *712*615738865*1#.

The phone requires its own enrollment, a Hormuud subscription, Phone and SIM
permissions, notification permission, EVC accessibility, an unlocked screen,
network, storage and battery readiness. Save the EVC PIN once and resume the
worker. It configures the exact subscription, polls automatically and accepts one
job at a time. Opening the app resumes the service; reboot/update also attempts
resume within Android restrictions. No ADB connection is required.

The native system telephony dialog is inspected at runtime, including actual
view IDs, OS-installed package and signing identity. A recognized carrier prompt
must match the name, mobile and amount before authorization and before PIN Send.
Unknown packages, ambiguous views and unrecognized languages fail closed. No
editable/password text or event text is read for evidence. Process death or a
lost response after submission quarantines the attempt; it is never replayed.

The final EVC text is retained as device-reported carrier-response evidence,
not invented as a carrier receipt reference. Backend checks name, number, amount,
carrier timestamp, live attempt and wallet balance. Matching success captures
partner principal plus the fee exactly once and records live fee revenue. An
ambiguous result holds reservations for reconciliation. Confirmed insufficient
balance releases reservations and earns no fee. Webhook endpoint validation and
existing authentication remain in force.

A newly provisioned physical wallet starts with unknown float and zero ledger
opening, not simulated money. Its first successful carrier response provides an
audited observation of amount plus remaining balance. Subsequent mismatches or
stale observations require reconciliation; the existing one-hour float freshness
guard remains. This is not a substitute for reconciling partner funding before
production use. The present development database contains historical synthetic
partner funding and test transactions.

Distribution uses the existing package and testing signing identity, version
code 3, minSdk 24 and targetSdk 37. The standalone non-debug directInstall APK
adds only the special-use foreground-service permission. Personal automatic
enrollment builds contain a single-use capability: share only with the intended
phone owner, never commit the APK or capability, and do not install the same
personal build on multiple phones. The personal code expires after 24 hours.

Software validation does not establish Samsung A16 compatibility. Owner tests
must verify installation, native dialog recognition, exact SIM routing, PIN
submission and actual carrier results. No live transfer was submitted by Codex.
