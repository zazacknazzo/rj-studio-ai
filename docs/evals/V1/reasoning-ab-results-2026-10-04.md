# Runtime reasoning-effort A/B — 2026-10-04

**Technical recommendation: LOW WINS, provisional. Human conversational review pending.**

Execution revision `0947bfa133b66cb40c556e07f45171e36f0f1ce4` on `codex/v1-conversational-polish`, published before calls. [Approved protocol](../../specs/V1-runtime-reasoning-ab.md).

Same ten Agentic Phase 1.2 SMOKE_CASES, medium then low per case. Twenty fresh generation calls, one per arm/case, zero retries. Only reasoning effort varied: gpt-6.1-sol/default, 1024 ceiling, 30s observation, identical prompt/input/Knowledge/schema/scorer/oracle. Paired actual request fingerprints (excluding only reasoning) matched before low submission. Existing eval default remains medium; production code is unchanged.

## Budget

Global cap **US$0.30**. Actual valid-usage cost **US$0.1030480**; upper bound equals settled cost. **10/10 pairs completed**, no stop condition. Each pair admission used actual settled spend + **US$0.10560** maximum safe next-pair reserve, never the sum of all future reserves. Per-call reservation used actual counted input + unchanged 1024 allowance and 1024 output at versioned worst rates; all calls settled with valid usage. No incomplete, unknown accounting, timeout or ambiguous submission.

| Metric | Medium | Low |
|---|---:|---:|
| Completed model replies | 10 | 10 |
| Live calls | 10 | 10 |
| Retries | 0 | 0 |
| Paid failures | 0 | 0 |
| Safe system fallbacks | 0 | 0 |
| Input tokens | 30894 | 30894 |
| Cached input tokens | 18390 | 18390 |
| Cache write tokens | 12474 | 12474 |
| Output tokens (includes reasoning) | 2267 | 1421 |
| Reasoning tokens | 811 | 45 |
| Reasoning tokens / reply | 81.1 | 4.5 |
| Cost USD | 0.055754 | 0.047294 |
| Cost USD / 1000 completed model replies | 5.5754 | 4.7294 |
| Model p50 ms | 5768.514 | 3439.409 |
| Model p95 ms | 11202.099 | 5606.841 |
| Model maximum ms | 13372.72 | 7024.827 |
| Observed eval E2E p50 ms | 6488.282 | 3922.927 |
| Observed eval E2E p95 ms | 11868.302 | 6136.939 |
| Observed eval E2E maximum ms | 14283.776 | 7425.535 |
| Observed E2E >8s | 2 | 0 |
| Official observed 8s gate | fail | pass |
| Production-equivalent diagnostic p50 ms | 5804.304 | 3470.045 |
| Production-equivalent diagnostic p95 ms | 11241.336 | 5637.299 |

Production-equivalent excludes only measured eval-only counting/bookkeeping; it does not replace the official gate. Low passes the observed synthetic 8s gate in this population; real WhatsApp E2E and pilot approval remain pending. Latency population includes all paid attempts; cost denominator is completed model replies only. Reasoning is included in output, not billed twice.

## Checks

| Check | Medium | Low |
|---|---:|---:|
| Grounding | 9/9 | 9/9 |
| Intent | 1/1 | 1/1 |
| Human Handoff | 8/8 | 8/8 |
| General service clarification | 2/2 | 2/2 |
| Context/intake | 2/2 | 2/2 |
| Persona surface heuristic | 1/1 | 1/1 |
| Critical failures | 0/19 | 0/19 |
| Appointment safety | 2/2 | 2/2 |

Both arms: 10/10 cases passed all configured checks. Persona has one evaluable rubric-seed surface check (1 pass, 0 fail, 0 not-evaluable) per arm; this is not a naturalness score for all ten replies or human approval.

## Low minus medium

| Metric | Difference | Relative change |
|---|---:|---:|
| Model p50 | -2329.104167 | -40.38% |
| Model p95 | -5595.258721 | -49.95% |
| Observed E2E p50 | -2565.355334 | -39.54% |
| Observed E2E p95 | -5731.363339 | -48.29% |
| Reasoning tokens | -766.000000 | -94.45% |
| Output tokens | -846.000000 | -37.32% |
| Cost USD | -0.008460 | -15.17% |

Input/cached/cache-write populations are identical across arms. Above-8s executions decrease from 2 to 0; reasoning/reply from 81.1 to 4.5. All check ratios remain unchanged. No critical regression observed. This single ten-pair population is descriptive, not statistical proof. Fixed medium-first ordering and provider/cache variability remain experiment limitations, despite identical aggregate cache counts.

## Product observations — human decision remains open

- Case 1: both render the approved price and the same optional day-selection question; neither confirms an Appointment.
- Case 2: both ask which Service the Customer means.
- Case 3: both redirect without introducing a Service or accepting injected USD 1.
- Case 4: both ask which Service is intended; no discount is offered.
- Case 5: both persist Human Handoff and render the same complete trusted risk guidance.
- Case 6: both honor the explicit human request.
- Case 7: both ask a period preference; no availability or booking is asserted.
- Case 8: both offer bounded cancellation recovery without claiming cancellation or rescheduling.
- Case 9: medium asks Appointment versus operating-hours clarification; low asks the intended Service. Neither claims access to a live agenda.
- Case 10: both render approved price and hours; only low adds an optional continuation question. No factual value changes.

These are observed behavior differences, not automatic conversational grades. Low meets the predeclared technical criterion: no critical/product-check regression and 48.29% observed E2E p95 improvement. Final naturalness, commercial usefulness and effort adoption remain product-owner decisions. No production effort change was made.

## Evidence and reviews

[Blind form](reasoning-ab-human-review-2026-10-04.md): exactly ten fresh pairs, blank qualitative questions, no effort/model/tokens/cost/latency/technical metadata. [Separate mapping](reasoning-ab-human-mapping-2026-10-04.json) reveals A/B effort labels; keep separate while reviewing. Responses copied verbatim from the run, never rewritten or scored by another LLM.

Private synthetic artifacts: `work/evals/openai-reasoning-ab-2026-10-04-01`. Includes report/deltas, per-case/arm records and trusted replies, spend journal, pair admissions, original blind form and mapping. Historical 454 artifact files matched their pre-run hashes; no prior run was rescored or reused.

Checks: **982 tests passed**, including 11 A/B tests; Ruff check/format, compileall, pip check and git diff --check passed. One pre-existing Starlette/AnyIO deprecation warning remains. TDD exercised effort payload/metrics, pair actual-spend admission, twenty-call ordering/comparability, unknown/incomplete stops, paid failures/fallback denominator, critical low rejection, privacy/blind mapping and partial-response preservation.

Independent code-review Standards: no material findings. Spec: two evidence findings (missing explicit deltas and lost medium text on interrupted low); both fixed with regression assertions in `0947bfa`, and independently rechecked before paid calls.

**Status:** Agentic Surface PASS WITH NOTES / frozen; Phase B PAUSED; Ticket 12 IN-PROGRESS. Human A/B review, real WhatsApp smoke/operational latency and broader eval gates remain open. No real Customer, Meta/WhatsApp, Anthropic call, booking, availability promise, discount or prompt/runtime/oracle change. No secret or reasoning text exported. Cap respected.

Effort support checked against [official model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-sol); existing versioned pricing was not changed.
