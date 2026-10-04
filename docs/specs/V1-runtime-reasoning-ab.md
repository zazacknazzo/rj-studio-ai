# V1 Runtime Latency — Reasoning Effort A/B

Status: approved

Product-owner approval: 2026-10-04, incremental pair budgeting. Baseline
`82afec4` on `codex/v1-conversational-polish`. Phase 1.2 is PASS WITH NOTES;
its conversational quality is frozen. Ticket 12 remains in-progress, Phase B paused.

## Experiment and boundaries

Exactly ten `SMOKE_CASES`, one synthetic call per case/arm, M1 L1 … M10 L10.
Only reasoning effort varies: medium vs low. Keep gpt-6.1-sol, default tier,
1024 output ceiling, 30s observation deadline, prompt, fixtures, Knowledge,
scorer, oracle and production code unchanged. No retries, Anthropic, real
Customer, WhatsApp/Meta, B1 or B2. Existing eval default stays medium.
Confirm paired request fingerprints excluding only reasoning are identical;
stop before submission on a mismatch. Historical replies are never reused.

## Incremental budget and stops

Shared hard cap US$0.30. Before each pair, actual settled spend plus the next
pair's maximum safe reservation must fit. Never sum all future reserves.
Use the adapter's existing enforced input-count limit 16,000 + unchanged
1024-token allowance and 1024-output ceiling for each arm. At versioned worst
input rate US$2.50/M and output US$10/M, the pair bound is US$0.10560.
This coarse bound avoids duplicate preflights; each call still reserves its
actual counted-input bound and settles with actual valid usage. No cached-token
discount assumed for reservation. One serial collector shares the existing
fsynced spend journal; no other work can spend between pair admission and calls.

Stop on critical safety failure, invalid/unknown usage, accounting/privacy
failure, incomplete/provider failure, timeout, comparability failure or insufficient
next-pair budget. Known paid failures count as cost and attempts, not completed
model replies; safe fallback is separate. Unknown cost retains its conservative
reservation and blocks further calls. Preserve allowlisted incomplete reason.
Latency above 8s does not stop safe observation. Official p95 observed E2E <=8s
gate remains unchanged; production-equivalent E2E is diagnostic, not gate evidence.

## Evidence and review

Report actual spend, pair-admission bounds, completed pairs, stop reason, per-arm
checks, input/cache/output/reasoning tokens, cost per 1000 completed model replies,
model and observed E2E p50/p95/max, diagnostic E2E p50/p95 and count above 8s.
Report low-minus-medium deltas and paired samples without judging wording equality.
Do not use an LLM judge or automatically score naturalness.

After at least six completed pairs, generate blank blind side-by-side review
questions and a separate randomized A/B-to-effort mapping. Technical recommendation
is provisional: LOW WINS only with all ten pairs, no critical/product-check
regression, and at least 20% observed E2E p95 improvement; MEDIUM WINS on critical
low regression or negligible gain (<5%); otherwise INCONCLUSIVE. This operationalizes
'material' for this small run, not a statistical or human-quality approval.
Human conversational review remains required even after technical LOW WINS.
