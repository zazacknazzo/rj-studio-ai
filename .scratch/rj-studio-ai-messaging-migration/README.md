# Messaging architecture migration

**Status:** ready-for-agent

**Baseline:** `d4a104f` (V1 Tickets 01–08)

## Objective

Replace the synchronous Twilio/TwiML coupling with durable ingress, AI
processing, and outbound delivery while retaining SQLite, single-process
operation, generation claims, ordering, and all implemented V1 behavior.
Twilio remains the development adapter. Meta WhatsApp Cloud API becomes the
production adapter.

## Preserved work outside the baseline

Commit `55919a7` remains intact on local branch
`codex/v1-grounding-policy-overrides`. It implemented the older Ticket 09
shape and is intentionally excluded from this migration baseline. Ticket 09 is
blocked until issues 01–05 below are complete; reusable tests or policy cases
may be reviewed later without cherry-picking the implementation wholesale.

## Ordered issues

1. Provider contracts and fake sender
2. SQLite durability gate
3. Durable outbox and provider-neutral delivery runner
4. Proactive Twilio outbound and statuses
5. Async processing and early acknowledgement
6. Meta production adapter

Issue 02 is separated from the original combined durability/outbox proposal so
SQLite guarantees can be verified before schema and delivery lifecycle changes.

## Shared invariants

- Inbound receipt, AI Reply generation, and Outbound Delivery are distinct.
- One provider inbound ID creates at most one inbound, one logical AI Reply, and one delivery intent.
- AI Reply + pending delivery + completed processing commit atomically in proactive mode.
- No SQLite transaction spans LLM, sleep, backoff, or provider I/O.
- Same-Conversation automation advances after Provider Acceptance or explicit legacy acceptance, never by persistence alone.
- `accepted` is not `sent`, `delivered`, or `read`.
- `unknown` is never automatically retried and blocks that Conversation.
- An expired outbound `sending` lease becomes `unknown`; it is not reclaimed for automatic resend.
- Pending work is recovered from SQLite after restart without provider retry.
- External delivery is never described as exactly once.
- Before send, revalidate delivery eligibility, owner, and Human Handoff policy.
- No Redis, broker, Postgres, horizontal scaling, SaaS, CRM, scheduling, or generic job framework.

## Plan review record — 2026-09-22

### Architecture consistency review

- Reconciled the implemented `d4a104f` synchronous runtime with the unimplemented ADR 0006 target.
- Removed spec exclusions that contradicted the approved executor and Meta work.
- Blocked Ticket 09 behind issues 01–05 and recorded the typed-segment/trusted-fact redesign requirement.
- Kept Ticket 06 historically done while assigning its delivery-visibility correction to issues 03 and 05.

### Migration safety review

- Split the SQLite durability gate from outbox migration.
- Changed unsafe blanket `accepted_legacy` backfill: unverified historical replies become unknown and require explicit reconciliation.
- Required migration ordering that backfills delivery rows before tightening completed-processing constraints.
- Made proactive/legacy delivery modes mutually exclusive and blocked rollback while unresolved proactive work exists.

### Adversarial distributed-systems review

- Changed stale outbound `sending` from auto-reclaim to unknown because a crash cannot prove whether submission occurred.
- Added durable retention for authenticated status callbacks that race ahead of local acceptance finalization.
- Preserved the residual provider-acceptance/lost-response ambiguity and in-flight Human Handoff race as explicit risks.
- Confirmed that local ordering ends at Provider Acceptance; provider-side delivery order after acceptance is outside the local guarantee.

### Residual risks accepted for the pilot

- Unknown may represent either an accepted Message or no submission; avoiding automatic duplicates can require manual intervention and can delay a reply.
- A provider request already in flight cannot be recalled when Human Handoff begins.
- The application issues sends in order, but cannot guarantee provider/device delivery order after acceptance.
- Durable work still needs a live process supervisor; SQLite preserves work but does not execute it while the application is down.
- Legacy-unverified rows block their Conversations until explicitly reconciled.
