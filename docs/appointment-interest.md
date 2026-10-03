# Appointment interest (Ticket 11)

V1 collects interest, not an Appointment. An `appointment_interest` decision
starts one Conversation-scoped episode. An active episode associates short
answers with its missing field even when the next Intent is `other`.

The approved [Conversational Polish amendment](specs/V1-conversational-polish.md)
now requires service, day and period/preferred time, with at most THREE committed
questions per episode. Exact time and professional preference are optional.
These are unverified Customer preferences, never proof of a Service,
Professional, appointment or available slot. No real schedule operation occurs.

`LLMDecision.appointment_preferences` adds nullable `preferred_day`; all fields
remain bounded, printable, verbatim excerpts from the current Message. Existing
combined day/period proposals remain readable. Day is stored separately so a
short period answer does not overwrite it. Legacy values survive unchanged;
old handoff/released episodes remain closed. Active preferences consume bounded
context as untrusted data. Selected policies, grounding, multi-Intent, technical
risk, human request and identity transparency still precede collection.

Cancellation permits one gentle offer to choose another day/time. Persisted
`recovery_offered` prevents repetition across retry/restart. Firm cancellation
or refusal skips retention; after the offer, confirmation or an unclear answer
hands off without claiming cancellation. Rescheduling collects new preferences
within the same three-question budget; that initial offer consumes one question.
Unknown change requests transfer to a person. Complete intake or the reply to
the last question ends collection with handoff for real confirmation.

Migration `0011_conversational_intake` extends the existing row with
`preferred_day`, `request_kind` (`interest`, `cancellation`, `reschedule`) and
`recovery_offered`. It replaces only the relevant checks, preserves all legacy
columns and other tables, and rolls back interrupted replacement. No historical
outbound becomes eligible, no old handoff reopens. The same generation owner,
episode token/cursor, atomic completion and release/purge fences apply.

Migration `0010_appointment_intake` adds the original current `appointment_intakes` row
per Conversation: episode token, state (`collecting`, `handoff`, `released`),
initial preferences, clarification count, awaited field, last inbound cursor,
handoff episode token, and update timestamp. The existing generation owner and
lease plus episode/cursor comparison fence completion. Intake update, AI Reply,
Outbound Delivery, processing completion and any handoff commit or roll back
together. External generation and delivery remain outside the transaction.

Any handoff ends collection and links the intake to that handoff episode.
Explicit release marks it `released`; it never revives suppressed Messages.
Future appointment interest starts an empty episode with a new token and
replaces the old row. Released preferences are not injected into LLM context
or reused. This is neither a Customer profile nor permanent CRM memory.

The explicit Message purge also deletes intake rows older than its cutoff
(default 90 days since their last update), including their preference text.
It retains the active handoff suspension; purge is not release. Startup and
webhooks never silently delete data. Conversation deletion cascades intake.
Back up before migration; downgrade refuses to silently discard the intake.

The operator can explicitly inspect the preference fields for a
selected Conversation:

```bash
.venv/bin/rj-studio-maintenance inspect-appointment-interest --conversation-id <id>
```

This explicit command displays Customer-provided preferences; run it privately,
do not copy its output into routine logs. `list-handoffs` remains metadata-only.
Local list/release semantics and residual in-flight delivery races remain in
[Human Handoff operations](human-handoff.md) and ADR 0008. Deterministic cases
and synthetic seeds do not certify real-model extraction/naturalness; Ticket 12
still owns that gate. Meta's live smoke remains a separate operational gate.

## Implementation and validation record

Baseline: `7c6b2309f73f16cfee5b96b5acc492e97d1c7f5d`, from
`codex/v1-ticket-10-durable-human-handoff`; implemented on
`codex/v1-ticket-11-appointment-interest-handoff`.

Changed files, grouped by purpose:

- Intake policy: `src/rj_studio_ai/appointment_intake.py`, `application.py`, `handoff.py`.
- Contracts/context: `src/rj_studio_ai/llm_decision.py`, `conversation_context.py`, `providers/anthropic.py`.
- Durability/operations: `src/rj_studio_ai/persistence.py`, `maintenance.py`, `migrations/__init__.py`, `migrations/versions/0010_appointment_intake.py`.
- Tests: `tests/test_appointment_intake.py`, `test_appointment_intake_migration.py`, `test_llm_decision.py`, `test_anthropic_generation.py`, `test_migrations.py`.
- Documentation: this file, `README.md`, `docs/ARCHITECTURE.md`, `CONTEXT.md`, `PRODUCT.md`, `ROADMAP.md`, `human-handoff.md`, `structured-decision.md`, `evals/V1/README.md`, `evals/V1/appointment-interest-cases.yaml`.
- Local tracker: `.scratch/rj-studio-ai-v1/issues/11-appointment-interest-handoff.md`.

2026-10-02: full `pytest` suite **510 passed**, including 70 new cases and
regressions through Ticket 10/M06; migration-focused run **28 passed**. Ruff
check, format check (127 Python files), compileall, pip check and Git diff check
passed. The existing Starlette deprecation warning remains.

Independent Standards and Spec reviews identified the same location/multi-Intent
regression. A red/green test proved the correction: noncritical approved fact
parts remain alongside the intake question. Both reviews confirmed closure;
no remaining blocker. No secrets or Customer data entered fixtures, and no
live-model evaluation, real smoke or Ticket 12 gate was executed.
