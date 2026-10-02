# 11: Collect appointment interest before handoff

**What to build:** Lívia can collect the minimum appointment-interest details, then safely hand the Conversation to RJ Studio without claiming an Appointment or actual availability.

**Blocked by:** 06: Build bounded Conversation Context; 07: Produce validated Intent decisions; 09: Enforce grounded factual replies and trusted overrides; 10: Make Human Handoff durable and atomic.

**Status:** done

## Context

V1 handles appointment interest only as conversational intake. Scheduling, availability, confirmation, changes, and cancellations remain outside its scope.

## Likely components

Conversation-scoped intake state, structured decision/application finalizer, Human Handoff reason/data, and webhook/persistence tests.

## Acceptance criteria

- [x] For `appointment_interest`, Lívia collects Service plus preferred day or period in no more than two short clarification interactions; Professional preference is optional.
- [x] Collected details persist with the Conversation sufficiently for the handoff while not becoming V2 CRM memory.
- [x] After the required details or safe limit, Human Handoff opens without promising availability or creating an Appointment.
- [x] Appointment changes, cancellations, and rescheduling route directly to Human Handoff.

## Required tests

- [x] FastAPI/SQLite tests for the two-turn clarification limit, optional Professional, retained handoff details, and no availability/Appointment claim.
- [x] Synthetic eval cases for appointment interest, change, cancellation, rescheduling, and absent detail.

## Non-goals

- Trinks, calendar lookup, real availability, Appointment creation, rescheduling/cancellation execution, follow-up, or CRM lead-stage logic.

## Implementation record

Baseline `7c6b2309f73f16cfee5b96b5acc492e97d1c7f5d`; feature branch
`codex/v1-ticket-11-appointment-interest-handoff`. Migration 0010 preserves
prior data and adds one bounded current episode. See `docs/appointment-interest.md`
for collection, release, explicit inspection and retention rules.

TDD covered exact current-Message preference proposals, short replies, restart,
retry/concurrent ownership, stale episode fencing, two questions, atomic rollback
at five write boundaries, change/cancellation/reschedule and Meta/Twilio webhook
seams. The 13 synthetic eval seeds exercise deterministic policy only.

Validation: 510 tests passed (70 added); migration-focused run 28 passed. Ruff
check/format, compileall, pip check and diff checks passed. Existing Starlette
deprecation warning remains. Full suite includes Tickets 01–10 and M01–M06.
Two-axis independent code review found one P2 location/multi-Intent regression;
a red/green synthetic test now preserves noncritical approved fact parts with
the intake question. Both axes confirmed closure and no remaining blocker.

No live provider calls, real smoke, credentials changes, new Salon Knowledge,
Appointment, availability lookup/promise, CRM or Ticket 12 gate. Residuals:
model extraction/Intent/naturalness still need live evals, lexical change
triggers are conservative, and ADR 0008's in-flight submission race remains.
