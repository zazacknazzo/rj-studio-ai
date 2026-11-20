# Bind Telnyx eligibility and submission identity before possible submission

Status: accepted within the explicitly authorized offline Ticket 10 scope.

Keep the legacy Meta/Twilio policy unchanged. Telnyx must use the first durable
receipt of a legitimate Customer Message with validated source time, separate
consent and the existing atomic channel/pause/handoff/owner gates. Strict expiry
and a durable local clock high-water favor refusal over accidentally reopening a
window after replay or backward clock correction. Template evidence is a separate
classification contract; plain AI Reply text cannot masquerade as a template.

Give each logical Outbound Delivery an immutable UUIDv4 and payload binding rather
than deriving identity from a lease or attempt. Persist the first submission time
and each attempt's marker. Telnyx documents bounded endpoint-specific idempotency,
but the offline fingerprint is not an HTTP byte-equivalence guarantee. Accordingly,
only proven local non-submission can retry here; possible submission remains
unknown and cannot be replayed automatically, including after key expiry. The
future sender must prove the exact request/response contract before broadening this
policy. Keep acceptance and early callback reconciliation atomic and preserve all
uncertain evidence. No SQLite transaction crosses I/O; CX-06 remains explicit.

Additive storage avoids rebuilding the outbox and preserves Tickets01–09. Explicit
consent/template provenance and real clock accuracy remain operational gates.
This decision grants no channel activation, HTTP implementation or Ticket11 authority.
