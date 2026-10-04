# Trusted Handoff Policy Gate — 2026-10-04

Approved runtime correction on `codex/v1-conversational-polish`, baseline
`b76e7febe0484edaf31050ed7d6d476afc6b9274` (published before edits).

## Cause and scope

REAL_RUNTIME_BUG: `finalize_reply` treated `decision.handoff=true` as sufficient
to call `_clarify`; MessageResponder normalized its reason and atomically
persisted a new episode. A valid release was not lost. Sanitization never
proved need. The new explicit gate denies model-only proposals, changing only
handoff/reason fields; existing trusted branches authorize their own reasons.
The same Reply AST is then rendered and validated normally. ADR 0008 records
the policy and the separately scoped model-Intent/recognition limits.

History, release, persistence, appointments/cancellation, Knowledge, prompts,
providers, oracle v2, scoring, model/pricing/output/timeouts are unchanged.
The prior oracle-v2 B1 stays at 50/53, 49 pass / one fail, B2 absent; its added
validity sidecar excludes it from the final gate due to the runtime change.

## Pre-paid validation

TDD first reproduced benign greeting + model handoff, without history/release.
Deterministic integration coverage exercises greeting/OTHER, preserved plans,
release + restart + replay + history, mandatory current risk/human/complaint/
legal/payment despite model=false, approved Knowledge conditions and bad refs.
Existing appointment/cancellation, active suppression and concurrency regressions
remain required. 31 new parametrized tests; full suite **831 passed**, focused
handoff/grounding/appointment/polish/trace checks **228 passed**. Ruff check/
format, compileall, pip check and diff checks passed. One existing Starlette/
AnyIO deprecation warning remains. Three independent reviews precede paid retest.

## Live gates

Isolated retest: prior handoff and suppression seeded deterministically, explicit
manual release and restart, then one live generation for “Oi”, US$0.20 cap.
If passed, a fresh 53-case B1 and conditional approved B2 share one US$5 ledger.
No historical samples enter new counts. Config remains gpt-6.1-sol / medium /
default / output 512 / observation 30s / zero retries. Product latency remains
observed billable p95 <=8s; diagnostic timing cannot replace it. Synthetic
Messages, isolated SQLite, fake Provider Acceptance only.

## Independent pre-paid reviews

All reviewed `b76e7fe...75fde4f`, independently, read-only:

- Product/spec: APPROVE, zero material omissions, scope creep or implementation
  findings. Revised model-only test expectations match the approved contract;
  trusted risk/Intent/Knowledge/appointment/cancellation coverage remains.
- Safety/handoff: APPROVE, zero material findings. Independently passed 248
  focused tests, 40 assertions across all familiar reason codes (benign plans
  denied, missing plans fail closed), and a pending-delivery/fake-acceptance/
  release/restart/replay scenario with terminal suppression preserved.
- Standards: APPROVE, zero documented violations or material design smells.
  Small typed gate at the existing finalizer seam, no new orchestration layer.

No paid call preceded these verdicts. Prior oracle review count clarification:
its fixture contained 13 grounding cases, not the reviewer’s original printed
14; all loaded cases were actually compared. Original records are unchanged.

Execution results: pending. Ticket 12 remains in-progress;
real Meta/WhatsApp E2E is pending and cross-provider comparison deferred.
