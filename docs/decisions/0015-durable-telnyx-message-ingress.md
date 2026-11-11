# Preserve inbound provenance beside the operational journal before ACK

Status: accepted for explicitly authorized Ticket 07 only.

Keep operational observations and human effects in the approved journal. Add minimal
inbound receipts in a separate side table rather than rebuild the journal parent and
risk cascading its aliases/effect receipts. The same record_webhook_events transaction
writes these receipts, admits Messages, applies pause and fences work. Store no extra
body or body hash; retained Message content detects contradictory logical replay while
available. Receipts retain identity after content purge, preventing re-admission.
They join the existing unbounded retention hold, requiring explicit Ticket 13 erasure
and replay policy before production. They are private data, not anonymized metadata.

Reject contradictory event/Message identity or ambiguous channel; never use a Meta
alias or original edit/revoke ID as a join key. Echo effects must be durable before
ACK. Same logical human Message does not repause; an unseen one does, regardless of
apparent age. Preserve the marker-to-HTTP limitation of ADR 0012.

Source provenance uses only a validated Meta timestamp carried in the authenticated
Telnyx body. It must not exceed event/local time, with no positive skew allowance at
resume. Missing/invalid time remains unavailable and Ticket 05 suppresses it after
resume. A phone-hidden Customer is namespaced as bsuid without mapping it to a phone;
future sender support must explicitly decode the address and validate eligibility.

Provide a dormant parser and offline durable ACK interface; no external route. Reject
unsupported callbacks, including not-yet-implemented status/lifecycle, rather than
acknowledge an empty batch. HTTP streaming and duplicate raw headers still belong to
Ticket 12. A local tuple exercises atomic multi-envelope persistence without claiming
a provider batch wire contract. No production channel is enabled by this decision.
