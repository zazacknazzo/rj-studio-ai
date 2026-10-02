# Appointment interest (Ticket 11)

V1 collects interest, not an Appointment. An `appointment_interest` decision
starts one Conversation-scoped episode. An active episode associates short
answers with its missing field even when the next Intent is `other`.

Required details are the desired service and preferred day **or** textual
period. Professional preference is optional. All three are unverified Customer
preferences, not evidence that RJ Studio offers a Service or that a Professional
exists or is available. No time is queried, reserved, or confirmed.

`LLMDecision.appointment_preferences` proposes nullable, bounded exact excerpts
of the current Customer Message. The policy rejects invented, padded, or
nonprintable excerpts; it never echoes these excerpts as salon facts. Existing
grounding, required Service policies, risk rules, multi-Intent validation and
identity transparency still take precedence. Model `reply_text` remains unused.
The bounded context includes active preferences as untrusted Customer data;
this frame consumes input budget and contains no internal IDs or timestamps.

One trusted question asks for the missing service or day/period. Only a
committed clarification consumes the counter. A complete first Message needs
zero questions; an incomplete episode can ask at most twice. After the reply
to the second question, even missing details cause Human Handoff. The trusted
confirmation says the team will confirm availability, never that it exists.
Changes, cancellation and rescheduling go directly to handoff, without intake
questions or asserting an existing Appointment.

Migration `0010_appointment_intake` adds one current `appointment_intakes` row
per Conversation: episode token, state (`collecting`, `handoff`, `released`),
three preferences, clarification count, awaited field, last inbound cursor,
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

The assuming operator can inspect only the three preference fields for a
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
