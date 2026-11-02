# 03 — Durable operational pause and generation fencing

Status: in-progress

Base: 4a9d22e4842f3aa573ba1438bda1cb913f0ab488.
Spec: docs/specs/V1-telnyx-coexistence-ticket-03.md.
Dependencies: Tickets 01/02 complete with independent PASS.
Acceptance: exact Conversation correlation, durable idempotent pause, atomic
journal/effect, stale-owner/revision fencing, terminal suppression/restart,
legacy/handoff compatibility, all required tests and independent reviews.

## Comments

- 2026-11-02: isolated branch from the approved baseline; Baileys preserved.
  Outbound safety belongs to Ticket 04; operator authentication/resume to 05.
  Unbounded journal retention remains a release blocker.
