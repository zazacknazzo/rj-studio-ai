# Fresh OpenAI low/v4 Phase B — stopped B1

Status: blocked. Ticket 12: in-progress. Agentic Surface APPROVED/FROZEN;
Human A/B LOW APPROVED. No production-readiness claim.

## Authorization and freeze

Product owner explicitly confirmed `v1-agentic-commercial-2026-10-04-v4`;
the previous v3 reference was outdated. Branch `codex/v1-conversational-polish`;
local and origin HEAD matched `42525e84fab0b65e42311d2db3a7ea00dde84795`
with a clean working tree before collection. No main merge.

Candidate: gpt-6.1-sol / low / default tier / output ceiling 1024 / observation
30s / zero retries. Production deadline and fixed/Anthropic selector unchanged.
Existing US$5 shared cap and US$1 checkpoint; B1 all 53 once, B2 conditional
70 additional executions under the existing repetition plan.

SHA256 provenance recorded before paid requests in local `plan.json`:

| Input | Digest |
| --- | --- |
| Oracle implementation | c8d9fa6c4f08bcdd10f317ba0c59a8a57e1650a9d0b65bee675e87d358b432bb |
| Suite | 97e71159775e24e58f0e1e7b0bae04615d2eae4200016faa2dfc052d0955012b |
| Knowledge | 6d1bd01715f4cd09a7d6c5a2b3e91f5eab6b1a944162642c86bbb924a5b050a5 |
| Canonical eval prompt/schema | 446936e4640aa1e85c00cc2425120cf02c33a23dd1c4bae6804c3782db3f0f92 |
| Persona source | ea7be0499cc2cd69407ba1dec339f1f4744e56fc1efeb2461216d2e2b38b75f7 |
| Decision source | 0422f35854dc84a7452dee286e0869e9ecc61be778e84abdafab9839512288ae |
| OpenAI eval adapter source | 4874b7ad19a8e697ca64977bb452b84cb84984909ee5635a7698fe37c9083ce3 |

Per-fixture hashes and all 228 tracked-file hashes also recorded. Every case
checked the freeze; post-stop verification found zero changes. All 529 previous
eval artifact files retained identical hashes. No result reuse or retrospective
rescore. Only this documentation was updated after the population stopped.

Short pre-live config, oracle/spec and budget/accounting reviews passed.
Unchanged baseline had 984 passing tests/all static checks; 76 focused eval
tests repeated before collection. Structural cases do not generate; injected
adversarial proposals remain deterministic coverage, not paid model input.

## B1 results

53 planned; 40 started/executed, 39 passed and one failed; 13 not executed.
`appointment-reschedule` caused `critical_failure`, stopping before case 41.
Its model output was complete and billable despite the failed behavioral check.

| Metric | Result |
| --- | --- |
| Critical failures (checks, not cases) | 1/44 |
| Grounding | 20/20 |
| Intent | 15/15 |
| Handoff | 17/17 |
| Appointment safety (no booking + handoff checks) | 7/7 |
| Context/intake checks | 6/7 |
| Commercial | 2/2 |
| Persona surface | 6 evaluable / 6 pass / 0 fail / 0 not-evaluable |
| LIVE_BEHAVIORAL executions | 40; 39 pass / 1 fail |
| DETERMINISTIC_ADVERSARIAL executions | 0; no injection in live |
| STRUCTURAL_CONTRACT executions | 0/3 planned; not reached |

Appointment safety's 7/7 does not erase the separate critical intake failure.
Persona surface checks are not automatic naturalness grades. B2: not executed.

## Cost and latency — partial population only

40 live calls, 40 completed model replies, zero retries/paid failures/safe
fallbacks/unknown billing. A semantic failure is not a provider-generation paid
failure. All 40 responses had valid usage; 40 reservations settled, no open
reservation. Independent Decimal ledger reconciliation matched US$0.1152439.
Pricing: `openai-standard-2026-10-02-v1`, unchanged.

Input 123,211 (includes cached 104,089 and cache-write 19,002); output 5,709
(includes reasoning 355). Total US$0.1152439; US$2.8810975 per 1,000 completed
model replies. No attempt/failure inflated the denominator. Hard cap/checkpoint
not reached. Cost gate passes only for the measured partial population.

| Latency | p50 | p95 | max |
| --- | ---: | ---: | ---: |
| Model HTTP | 3.565s | 5.785s | 7.863s |
| Observed E2E, official | 4.006s | 6.164s | 8.232s |
| Production-equivalent, diagnostic only | 3.589s | 5.819s | 7.896s |

Observed E2E >8s: 1/40. The official p95 gate passes on this partial population;
it does not approve all 53 cases or real WhatsApp E2E. Diagnostic latency never
substitutes for the observed gate. No optimization occurred during collection.

## Failure evidence and separate read-only diagnosis

Synthetic Customer: “Quero remarcar para amanhã”. Trusted persisted reply:
“Claro! Qual serviço você quer remarcar?” Model Intent appointment_change,
authorized target desired_service, no facts/refs, no handoff/fallback.
`no_booking_claim=pass`, `handoff_policy=pass`, `bounded_intake=fail`.
Response completed, usage/pricing valid, no provider/accounting error.

Confirmed **ORACLE DEFECT**, reproduced offline using the real MessageResponder,
SQLite and unchanged score_appointment: with the same synthetic Message and
question, omitting preferences yields count=1 and all three checks pass;
proposing the exact Customer excerpt preferred_day="amanhã" persists that day,
count=1, request_kind=reschedule, and fails only bounded_intake. The fixture's
empty preferences produces expected preferred_day=None, rejecting valid source
evidence. No response wording change is needed to trigger the false negative.

Exact cause of this live failure remains **unproven**: its persisted intake and
model preference proposal were not retained in the privacy-safe sample and the
temporary database was removed. The reproduced oracle defect is a strong
explanation, not proof of the original stored values. No claim that runtime
state was correct, no population invalidation/rescore and no passing replacement
result are fabricated. The original one critical failure remains recorded.

Next separate round: preserve this population, capture bounded intake field
evidence, test valid source-day preservation and invented-preference rejection,
then correct the oracle's source-derived expectation only if authorized. No
runtime/prompt/facts/scorer change or paid retest occurred after the stop.

## Evidence and remaining gates

Local root: `work/evals/openai-phase-b-low-v4-2026-10-04-01/`.
Contains plan, frozen hashes, pre-live reviews, spend journal, individual samples,
phase-B1.json, report.json and audit-packet.json/md (40 synthetic responses).
No new automatic human scores. B2 has no paid samples.

Final OpenAI-only gate blocked; Phase B is not complete. Agentic Surface and
low human approval remain frozen. Cross-provider comparison deferred. Production
OpenAI promotion requires a separate approved round even after Phase B passes;
real Meta/WhatsApp smoke remains pending. No real Customer, Meta/WhatsApp,
Anthropic, secret disclosure, .env edit, production provider change or main merge.

After-stop checks: full suite 984 passed (one existing Starlette/AnyIO
deprecation warning); Ruff check, Ruff format --check, compileall, pip check and
git diff --check passed. Only result/decision/index/ticket documentation changed.
