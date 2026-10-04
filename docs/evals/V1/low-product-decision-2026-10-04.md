# Lívia V1 — Human A/B Review: LOW APPROVED

Status: approved

Product-owner decision recorded 2026-10-04. The human review explicitly approves
low qualitatively, based on the [fresh ten-pair A/B](reasoning-ab-results-2026-10-04.md).
No automatic naturalness grades or numerical averages are inferred. The original
run's collection-time review status and raw responses remain unchanged; existing
manual notes in the blind form are preserved.

Adopt `gpt-6.1-sol`, reasoning `low` as the V1 OpenAI candidate/default.
Keep default tier, 1024 output ceiling, 30s eval observation, existing production
deadline, accounting, safe failure, incomplete metadata and zero retries.
Explicit medium override remains available for future evaluation; no escalation
or provider switching is implemented. Anthropic and messaging remain unchanged.

The existing OpenAI implementation is eval-only. Production selection still
supports fixed/Anthropic; this default change does not add an OpenAI production
adapter, alter `.env`, or authorize autonomous deployment.

## Evidence and conversational freeze

Low: critical failures 0/19, grounding 9/9, handoff 8/8, appointment safety 2/2,
observed E2E p95 6.137s and 0/10 above 8s. Human conversational quality approved;
reasoning usage and cost lower than medium. Agentic Surface is approved/frozen.
No prompt, commercial steering, Reply AST/phrases, next_action, appointment or
cancellation behavior, handoff surface, Knowledge or oracle change is authorized
for minor wording differences.

## Fresh Phase B authorization and unresolved oracle name

The product owner authorizes a fresh B1 with all 53 cases and conditional B2
under the existing protocol: shared US$5 cap, US$1 spend checkpoint, one initial
execution per case and at most three total probabilistic executions per case.
No prior population is reused. B2 requires complete passing B1 semantic,
accounting, observed E2E p95 <=8s and cost <=US$10/1000 completed model replies.
Real safety/provider/accounting failures stop collection; valid wording variants
are not failures. No live optimization, retries, Anthropic or real messaging.

The instruction names Oracle v3, but code and the approved A/B used
`v1-agentic-commercial-2026-10-04-v4`; v3 is a historical replay variant.
The oracle is not edited or rolled back. Its exact name must be resolved by the
product owner before paid Phase B. Configuration tests/reviews may proceed.

Ticket 12 stays in-progress. Report evidence and remaining material gates before
any completion recommendation; never mark V1/Ticket 12 complete automatically.

## Pre-live checks — 2026-10-04

984 tests passed (two new default/override integration cases). Ruff check,
format check, compileall, pip check and git diff --check passed. Default-low
assertions first failed against medium, then passed after the two default-only
source edits; the explicit-medium path remained green.

Configuration review: model/tier/1024/30s observation/production 10s deadline,
pricing, zero retries and incomplete/accounting handling unchanged. Independent
Standards/safety review: no material findings. Independent eval/spec review: no
findings in adoption; exact oracle clarification remains the pre-live dependency.
The suite is still 53 cases: 50 LIVE_BEHAVIORAL and three STRUCTURAL_CONTRACT.

No paid call, B1 or B2 occurred in this adoption step. No new cost/latency or
semantic gate is claimed from old populations. Human A/B quality is approved;
V1/Ticket 12 are not marked complete. No Customer, messaging or Anthropic calls.
