# Coordinate LLM generation with durable SQLite claims

Status: accepted

V1 will keep one durable generation record per inbound Message. A short SQLite
`BEGIN IMMEDIATE` transaction creates or acquires a claim with an owner token,
a 30-second lease, and a maximum of two attempts. The LLM call runs outside the
transaction. A second short transaction permits only the current owner to
persist the AI Reply and mark the generation completed.

The generation states are `processing`, `retryable`, and `completed`. A
completed reply is replayed exactly. An active claim prevents concurrent LLM
calls for the same Message. An expired claim may be acquired after a restart;
an old owner cannot complete it. Exhausted or permanent failures persist one
safe Human Handoff reply instead of retrying indefinitely.

Messages within one Conversation are processed in arrival order so that later
generation observes earlier state. A blocked later Message is persisted and may
resume only through a provider retry or an explicit local recovery operation
after its predecessor reaches a terminal result. Recovery lists pending or stale
Messages and acts only on the oldest eligible Message in a Conversation. It
preserves claim ownership and records a terminal result through safe retry or
Human Handoff. Fully autonomous recovery would require a future executor and is
deferred. Conversations may run in parallel. V1 uses one active application
instance, one persistent SQLite database, and no Redis, queue, worker, or
horizontal scaling.

An inbound received during active Human Handoff is persisted with the terminal
processing result `suppressed`. It has no generation or AI Reply, and later
retries receive only the provider acknowledgement even after restart or manual
release. Release changes automation only for future inbound Messages.

When a generation decision activates Human Handoff, one transaction validates
the current owner and Conversation state, persists the inbound terminal result
and optional one-time confirmation AI Reply, completes the generation when one
exists, stores the handoff state and reason, and releases the claim as
applicable. A concurrent manual release cannot validate a stale owner or expose
a confirmation while the Conversation remains automatic.

The generation lease is independent of the webhook deadline. The 30-second
lease coordinates owners and restart recovery; the 10-second monotonic deadline
starts at inbound admission and covers database waits, ordering waits, retries,
generation, validation, final persistence, rendering, and the HTTP response.
Every stage uses only the remaining budget, with time reserved for finalization.

A process can fail after the LLM returns but before the reply is committed. A
later attempt may then incur a second provider charge, although the database
still permits only one persisted AI Reply. Removing that residual window would
require provider-side idempotency or additional distributed infrastructure and
is deferred until evidence justifies it.
