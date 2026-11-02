# Coexistence Ticket 03 — durable pause and generation fencing

Status: approved

User authorization: 2026-11-02; base 4a9d22e4842f3aa573ba1438bda1cb913f0ab488.
Only Ticket 03 is authorized. The current request supersedes the original plan
where that plan includes outbound cancellation or external operator commands.

## Required behavior

HumanMessageObserved is journaled and its pause effect commits in the same
transaction. A separate effect receipt distinguishes event persistence from effect
application, including observations already stored by Ticket 02. Exact provider,
channel and Customer identity are required; aliases never select a Conversation.
An existing Conversation must have exactly the matching channel evidence (or an
existing matching control). Missing/contradictory channel evidence remains in the
journal without an applied effect. A first human observation may create only a
Conversation identity/control before any inbound Message. No Message is invented.
The existing single-channel-per-Conversation model is retained, not generalized.
Inbound channel changes for a controlled Conversation are rejected rather than
merged into the wrong pause. No inference across providers or opaque addresses.

A unique logical human Message identity (provider/channel/Customer/Message ID)
applies once even across distinct event envelopes. Shared aliases do not merge
identities. Distinct human Messages increment a durable revision, including late
observations. Replay does not alter revision or timestamps. Startup applies
unapplied journal evidence before executors start; it never equates an old receipt
with an already applied pause. Unresolvable evidence remains unapplied.

A side table holds paused state, channel, revision and timestamp. Pause suppresses
all retryable/processing Messages, clears owner/lease, and preserves attempt count.
New inbound during pause is terminal suppressed; timeout, new inbound, recovery,
restart or policy-handoff release cannot revive it. No resume operation is added.
A claim snapshots the operational revision in SQLite; finalization validates
owner, lease, pause state and captured/current revision in its own transaction.
Triggers protect alternative inserts/updates; normal legacy constructors remain
unchanged. No SQLite transaction spans LLM work. Already running LLM work may
finish/consume computation, but cannot persist a new reply after pause commits.

Human Handoff is independent. Its state/reason/episode are not changed by pause.
Completed replies, outbox states/claims/attempts and unknown are not rewritten.
The pause/finalization race is ordered by SQLite commit: if completion wins, its
reply remains; if pause wins, completion fails. Ticket 04 owns outbound fences.

## Migration and retention

Migration 0015 adds controls/effect receipts and a generation revision column.
The old CHECK prohibited suppressed rows with previous attempts; rebuild only the
leaf message_processing table to remove that restriction, preserving all rows,
FKs/indexes/triggers and attempt counts. Do not rebuild Conversations or Messages.
Controls cannot be cascade-deleted by retention. Raw Message purge may remove
content, but retains a paused Conversation; explicit Conversation deletion rejects
an active operational control. Journal/effect receipts remain held without expiry.
Unbounded retention is a release blocker, not a production retention solution.

## Tests and exclusions

Deterministic barriers test pause before claim, during LLM, stale completion,
both orders of commit races, restart, expired/exhausted recovery, duplicate echo,
unresolvable/ambiguous identity, mixed batch rollback, separate Conversations,
policy handoff, legacy providers, no new reply after pause and private errors.
Migration tests cover existing evidence, triggers and rollback. Full suite, Ruff,
formatting, compilation and diff checks plus independent Standards/Spec reviews.
No Telnyx parsing/webhook/API, sender, authentication, resume, outbound cancellation,
CRM, SaaS, intelligence/prompt/persona/model/grounding change. No external calls.

## Release limits

Replies already persisted may still be sent, including a handoff confirmation;
pending and in-flight sends are unchanged in this ticket. No complete takeover
safety until Ticket 04; no usable authenticated human operations until Ticket 05.
Ticket 04 remains unstarted and requires separate authorization.
