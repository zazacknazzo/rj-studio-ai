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
generation observes earlier state. Conversations may run in parallel. V1 uses
one active application instance, one persistent SQLite database, and no Redis,
queue, worker, or horizontal scaling.

A process can fail after the LLM returns but before the reply is committed. A
later attempt may then incur a second provider charge, although the database
still permits only one persisted AI Reply. Removing that residual window would
require provider-side idempotency or additional distributed infrastructure and
is deferred until evidence justifies it.
