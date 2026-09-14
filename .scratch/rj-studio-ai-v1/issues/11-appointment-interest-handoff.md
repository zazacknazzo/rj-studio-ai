# 11: Collect appointment interest before handoff

**What to build:** Lívia can collect the minimum appointment-interest details, then safely hand the Conversation to RJ Studio without claiming an Appointment or actual availability.

**Blocked by:** 06: Build bounded Conversation Context; 07: Produce validated Intent decisions; 09: Enforce grounded factual replies and trusted overrides; 10: Make Human Handoff durable and atomic.

**Status:** ready-for-agent

## Context

V1 handles appointment interest only as conversational intake. Scheduling, availability, confirmation, changes, and cancellations remain outside its scope.

## Likely components

Conversation-scoped intake state, structured decision/application finalizer, Human Handoff reason/data, and webhook/persistence tests.

## Acceptance criteria

- [ ] For `appointment_interest`, Lívia collects Service plus preferred day or period in no more than two short clarification interactions; Professional preference is optional.
- [ ] Collected details persist with the Conversation sufficiently for the handoff while not becoming V2 CRM memory.
- [ ] After the required details or safe limit, Human Handoff opens without promising availability or creating an Appointment.
- [ ] Appointment changes, cancellations, and rescheduling route directly to Human Handoff.

## Required tests

- [ ] FastAPI/SQLite tests for the two-turn clarification limit, optional Professional, retained handoff details, and no availability/Appointment claim.
- [ ] Synthetic eval cases for appointment interest, change, cancellation, rescheduling, and absent detail.

## Non-goals

- Trinks, calendar lookup, real availability, Appointment creation, rescheduling/cancellation execution, follow-up, or CRM lead-stage logic.
