# 10: Make Human Handoff durable and atomic

**What to build:** A sensitive Conversation can transition atomically to Human Handoff, receive one confirmation, suspend automation, and later be explicitly released without reviving suppressed Messages.

**Blocked by:** 01: Add durable generation claims; 07: Produce validated Intent decisions; 09: Enforce grounded factual replies and trusted overrides; Messaging Migration 03–05.

**Status:** done

## Context

Human Handoff transfers responsibility to RJ Studio. It is durable Conversation state, not merely LLM text, and must be safe through retries, crashes, restarts, a concurrent manual release, and outbound work already pending. Before provider submission, delivery eligibility, owner, and handoff policy are revalidated. Handoff can cancel work not yet submitted; an already in-flight provider request is an explicit residual race.

## Likely components

Migration for Conversation handoff state/reason, atomic SQLite finalization, webhook response path, local list/release operation, and FastAPI/persistence tests.

## Acceptance criteria

- [x] One transaction records, as applicable, the inbound terminal result, one confirmation AI Reply, completed generation, active Conversation handoff with reason, and claim release; no partial state is observable.
- [x] Active Human Handoff causes later inbound Messages to persist as terminal `suppressed` and receive provider acknowledgement without an AI Reply or LLM call.
- [x] A retry of a suppressed inbound remains suppressed after restart and after manual release; release affects future inbound Messages only.
- [x] Local list/release operations are explicit and omit full Message bodies from routine output.
- [x] Completion and release both validate the current Conversation state and owner token, so a stale owner cannot finalize or reactivate automation.

## Required tests

- [x] FastAPI/SQLite tests for explicit human request, complaint, technical risk, safe confirmation replay, suspension, restart, and release.
- [x] Transaction-failure test proves no confirmation can persist while the Conversation remains automatic.
- [x] Race test covers generation finalization versus manual release.
- [x] Regression test: handoff → inbound B suppressed → acknowledgement lost → release → retry B → acknowledgement only, no AI Reply and no LLM call.

## Non-goals

- External notification delivery, on-call routing, calendar integration, CRM workflow, or automatic release.

## Implementation record

Implemented from Ticket 09 commit `89c7d23` on
`codex/v1-ticket-10-durable-human-handoff`. Migration 0009 preserves the M06
data and adds Conversation episodes plus delivery submission fencing. See
`docs/human-handoff.md` for list/release commands and ADR 0008 for trade-offs.

Validation: 440 tests pass, including 35 new migration/handoff cases. Ruff,
format, compileall, pip check, and diff checks pass. Review against the ticket,
V1.6, ADRs 0005–0007, and AGENTS invariants found no remaining blocking issue.
Purge preserving active handoff, recognized symptom guidance on generation
failure, legacy replay gating, and late proven-not-accepted results were
corrected/tested during review. Provider requests already authorized remain an
explicit residual race; unknown/failed outcomes still require reconciliation.
No real smoke, provider/credential changes, appointment collection, or CRM work.
