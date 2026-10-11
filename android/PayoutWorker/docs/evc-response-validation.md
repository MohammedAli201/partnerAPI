# EVC recipient validation

The recipient name comes from `request_payload.beneficiary.name` (or
`request_payload.recipient_name`). Sender names are never used as recipient names.
The transaction retains its canonical `+252` phone number. Only the carrier
command and response comparison use the local nine-digit number.

Named assignments bind the name into payload hash version 2. The PIN prompt must
match the assigned name, amount and number. Name comparisons ignore case and
repeated whitespace; spelling differences are rejected. Final responses use the
EVCPLUS grammar supplied in the user's screenshot and must match all three
fields. Unknown responses remain unconfirmed. The screenshot is a parser fixture,
not evidence for any queued payment. Its response contains no transaction
reference, so the parser does not fabricate one.

`POST /payouts/prepare-ussd` validates input and returns a command preview with
`payment_executed: false`. It neither creates nor executes a payment. Automatic
real-payment dispatch, verified device profile, local PIN provisioning and
independent backend settlement remain prerequisites; this parser change does
not enable them. The existing SMS test route remains separate.
