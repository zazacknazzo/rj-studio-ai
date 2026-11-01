# 02 — Operational journal and scoped deduplication

Status: in-progress

Base: 98bc4440daaa84d5c58d6c2e4e8d7fccccdd319e.
Spec: docs/specs/V1-telnyx-coexistence-ticket-02.md.
Dependency: Ticket 01 (PASS). No authorization for Ticket 03.

Acceptance: versioned migration; scoped dedupe; private durable operational
observations and references; atomic mixed batches; restart/concurrency/rollback;
legacy compatibility; explicit retention hold; full offline checks and two
independent reviews. No operational effects, Telnyx parsing, network or sender.

## Comments

- 2026-11-01: user authorized Ticket 02 only. Dedicated worktree and branch created
  at the approved commit. The narrower authorization supersedes the original
  plan's control-state/revision scaffolding; that belongs with actual effects.
