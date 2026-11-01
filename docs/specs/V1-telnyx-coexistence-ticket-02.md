# Coexistence Ticket 02 — operational journal

Status: approved

Authorization: explicit user approval of Ticket 02 on 2026-11-01, based on
98bc4440daaa84d5c58d6c2e4e8d7fccccdd319e. Tickets 03–13 are not authorized.
The current authorization narrows the original plan: persist observations only;
no pause/resume, cancellation, operator authentication or channel activation.

## Contract and acceptance

- Persist HumanMessageObserved, MessageEdited, MessageRevoked and
  ChannelAvailabilityChanged without creating Conversations, Messages,
  generation claims, AI Replies or deliveries.
- Journal identity is (provider, scope_kind, scope_id, event_id). Message events
  use channel scope; account lifecycle uses its explicit account scope. Identical
  IDs in different scopes remain distinct. A conflicting reuse of the same
  event identity rejects the entire batch; it is not an update or a silent ACK.
- Preserve kind, origin, provider Message ID, original Message reference,
  namespaced aliases, event time, optional Message time and first receipt time.
  Canonical timestamps normalize to UTC. Aliases form an unordered set.
- References are evidence, not associations. Shared aliases or original Message
  references do not collapse distinct events, unite Customers or resolve an
  ambiguous Message. No foreign key to a guessed Conversation/Message exists.
- Deduplication suppresses identical event observations, not logical messages.
  Distinct envelope IDs for the same human Message remain separate observations.
  Future effects must deduplicate logical activity separately using verified
  identities; this ticket does not implement those effects.
- One BEGIN IMMEDIATE transaction covers all operational rows, their aliases,
  existing inbound admission and existing delivery-status handling. Failure at
  validation, SQL execution or commit means no successful ACK and no partial
  batch. No external I/O occurs in the transaction.
- Legacy Meta/Twilio and their inbound/status identities, acceptance, early status,
  unknown, ordering, claims and handoff retain their existing semantics. Optional
  inbound/status metadata is not journaled by this ticket; enriched status
  correlation and service-window evidence belong to Tickets 08 and 10.
- No parser, route, sender, credentials, network integration or intelligence edits.

## Schema and privacy

Migration 0014 adds operational_events and operational_event_aliases only.
Unique event scope and alias-per-observation indexes enforce idempotency. CHECKs
separate lifecycle from Message shapes. Alias rows reference the journal with
ON DELETE CASCADE. Schema readiness checks include the added structures.
No raw payload, Message text or free-form provider error is stored in this journal.
Identifiers and addresses needed for future correlation are private database data;
errors/logs expose neither their values nor SQL parameters. No journal export,
inspection endpoint or report of external identifiers is introduced.

## Retention

Operational evidence is held for at least 90 days and, in this ticket, until an
explicit later retention operation is approved and implemented. There is no
automatic expiry, purge at startup, or deletion by the raw-Message purge or
Conversation deletion commands. Those commands retain their documented scope;
they do not claim to erase the operational journal. This deliberate hold prevents
replay re-admission and loss of future unresolved-operation evidence. It implies
unbounded journal growth in this offline stage and is not a production retention
solution. Ticket 13 must implement/review explicit erasure, bounded retention and
minimal dedupe tombstones, protecting active operational episodes, unresolved
outcomes and open channel cycles, before production enablement. No hash of a
phone number is presented as anonymization. Raw Message retention stays governed
by ADR 0004, including its existing explicit commands and 90-day default.

## Verification

Deterministic temporary SQLite tests cover identical duplicates, cross-scope IDs,
reference/alias ambiguity, out-of-order events, mixed batches, full rollback,
concurrent writers, restart/replay, SQL/commit failures before HTTP ACK, legacy
migration with data, compatibility, zero generation from operational events,
privacy, retention and schema/durability checks. Full suite, Ruff, formatting,
compilation and diff checks must pass. Independent Standards and Spec reviews
are required. No real customer data or network access is used.
