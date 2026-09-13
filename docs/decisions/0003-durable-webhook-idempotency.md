# Make webhook reply preparation durable and idempotent

Status: accepted

Use `(provider, provider_message_id)` as the inbound idempotency key. Store the
inbound Message and its Automatic Reply in one SQLite
`BEGIN IMMEDIATE` transaction. The outbound row references the inbound row,
and a unique database index permits only one logical reply for that inbound
Message.

Every sequential or concurrent retry reads and renders the stored reply,
including after a process restart or an HTTP-response failure. In-memory locks
are not part of correctness.

This guarantees exactly-once logical reply preparation and persistence. It
does not guarantee exactly-once delivery by Twilio or WhatsApp; delivery status
callbacks remain deferred.
