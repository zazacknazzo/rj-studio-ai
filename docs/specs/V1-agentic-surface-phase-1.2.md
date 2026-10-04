# V1 Agentic Surface — Phase 1.2

Status: approved

Approval: product-owner instruction of 2026-10-04, Commercial Initiative +
Generation Headroom. Baseline `12c652c` on `codex/v1-conversational-polish`.
Phase B stays paused; functional checks do not approve human product quality.

## Scope

Strengthen shared planning instructions for consultative commercial initiative.
Reuse advisory `next_action`; advancing a sale or qualifying interest chooses
neither wording nor an operational action. Continuation is optional and
context-dependent. No catalog additions, fixed questions, automatic CTA or
commercial decision tree. Observe continuation and possible early closure as
soft product signals, separately from factual safety and human review.

Capture `incomplete_details.reason` using an allowlist only. Never store provider
payloads, output text or reasoning in diagnostics. Incomplete remains a paid
failure, with valid usage billed and a separate safe system outcome. No retry.

Centralize the generation ceiling at 1024: live eval previously 512; the existing
Anthropic runtime default/upper bound previously 200. There is no OpenAI production
adapter. Honor explicit lower runtime configuration, without editing local `.env`.
Keep model, effort, tier, timeouts, accounting and product latency gate unchanged.
The ceiling includes reasoning and structured output; it is not a consumption goal.

## Validation and execution

TDD at existing public decision/finalizer, provider request, diagnostics,
responder and live-accounting seams. Cover optional/different continuation,
noncommercial and safety contexts, trusted price and discount/ambiguity, no action
from advisory planning, complete/incomplete responses, safe fallback, privacy,
zero retry and cap enforcement. Full suite, Ruff check/format, compileall,
pip check and diff check; four independent product, architecture, safety and
accounting reviews before any paid calls.

First run exactly the existing direct-price, ambiguous-price, discount and
technical-risk cases once with a shared US$0.40 cap. OpenAI gpt-6.1-sol, medium,
default tier, output 1024, observation 30s. Stop on generation/accounting/privacy
or semantic failure. Price continuation is a soft observation, not a required CTA.
Only 4/4 pass permits a new ten-case smoke, US$1 cap, no retries, no Phase B.
Latency above 8s is reported as a gate failure, without stopping safe observation.
Preserve historical runs. A new human packet contains only completed trusted
responses, no scores; product approval remains explicit and human-owned.

## Unchanged boundaries

No facts/Knowledge, factual renderer, handoff/appointment authority, cancellation
limits, availability, provider actions, persistence/messaging change, Meta/Twilio,
Anthropic live call, real Customer or latency optimization. No oracle expectation
relaxation. ADR 0009 remains proposed and Ticket 12 remains in-progress.
