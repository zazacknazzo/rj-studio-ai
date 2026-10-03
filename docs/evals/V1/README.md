# V1 eval suite

Current product round: [approved Conversational Polish](../../specs/V1-conversational-polish.md).
Product milestone: **V1 Conversational Polish: COMPLETE / APPROVED**.
Ticket 12 remains in-progress; the newly authorized B1/B2 execution is a
separate live gate, using fresh records and one shared US$5 budget.
Latest execution: [fresh Phase B — stopped B1](openai-phase-b-2026-10-03.md).
B1 stopped at case 27 on a deterministic-proposal/live-oracle mismatch; raw
critical failures remain 2/13. B2 not executed; no rescore or code correction.
Current human decision: [APPROVED qualitatively by the product owner](conversational-polish-human-review-2026-10-03.md).
Closure evidence: [cancellation correction, isolated retest and fresh smoke 04](cancellation-recovery-2026-10-03.md).
Retest 1/1 and fresh smoke **10/10**; critical 0/17, observed p95 6,270.32ms
passes the unchanged 8s gate for this run. No additional numerical ratings or
retrospective average. Qualitative human approval and functional pass released
Phase B after that smoke 04 stage; its later stopped execution is linked above.
Ticket 12 stays in-progress,
real Meta/WhatsApp E2E remains pending. Historical evidence is unchanged.

## Historical execution records

Latest authorized fresh smoke: [run 03 cancellation recovery failure](conversational-polish-smoke-03-2026-10-03.md).
Eight of ten cases ran, seven passed; model-requested immediate handoff omitted
the cancellation recovery offer. Injection relevance passed. No prompt/runtime
change or subsequent call; observed p95 8,055.01ms fails the unchanged 8s gate.
The new eight-answer human form is partial and unscored. Ticket 12 in-progress;
Phase B not executed.

Latest authorized correction: [shared relevance instruction and isolated retest](factual-relevance-instruction-2026-10-03.md).
The unnamed-Service injection retest passed once with no rendered facts or
handoff. Shared instructions changed; deterministic grounding remains intact.
This does not approve a new complete smoke. No further live call or Phase B.

Previous fresh smoke: [run 02 factual relevance failure](conversational-polish-smoke-02-2026-10-03.md).
The corrected oracle stopped after 3/10 cases: corte was introduced without an
identified Service. Two cases passed; seven were not executed. No prompt/runtime
change followed; the new three-answer human packet is partial and unscored.
Ticket 12 stays in-progress and Phase B was not executed.

Implementation and fresh stopped smoke: [Conversational Polish result](conversational-polish-2026-10-03.md).
Three of ten cases executed (two pass, one semantic failure); no further live
call or Phase B. The new three-answer human packet is partial and unscored.
Product-owner correction: [injection relevance contract](injection-relevance-correction-2026-10-03.md)
classifies the unnamed-Service failure as a fixture/oracle issue. Original run
records retain their original results; [partial human scores](conversational-polish-human-review-2026-10-03.md)
are recorded without an overall score. No fresh paid run or gate approval.
The previous semantic 10/10 smoke failed product-owner human UX review. Phase B
remains blocked; new evidence requires fresh unscored human review. Synthetic
price/discount and appointment expectations now follow that explicit amendment;
factual prohibitions, invalid refs, mandatory policies and durable handoff
remain enforced. Old runs and packets are preserved unchanged. The historical
critical-scenario label `cancel_reschedule_without_handoff` now checks bounded
collection and eventual handoff, not immediate handoff on the first request.

Previous authorized step: [latency breakdown and ten-case smoke](latency-breakdown-smoke-2026-10-03.md).

Previous isolated retest: [eval observation deadline](observation-deadline-2026-10-03.md).

Previous diagnosis: [Responses usage provenance](usage-diagnostic-2026-10-03.md).

Latest authorized step: [shared multi-intent instruction and controlled retest](multi-intent-instruction-correction-2026-10-03.md).

Targeted follow-up: [multi-fact handoff diagnosis](multiple-facts-diagnostic-2026-10-02.md).

Current execution amendment: [512-token OpenAI evaluation](openai-smoke-512-2026-10-02.md).
Historical diagnostic run: [200-token partial evaluation](openai-partial-2026-10-02.md).
Anthropic comparison is deferred by the product owner. Ticket 12 remains
in-progress; comparative acceptance and human review are not complete.

Ticket 12 Phase 1: **harness implemented / live model gate pending**.
`suite.yaml` indexes **53 synthetic cases**: 14 Intent, 6 persona, 13 grounding,
13 appointment episodes, 4 durable handoff episodes and 3 context cases.
Eleven explicit critical-scenario groups require zero prohibited outcomes.
The original 45 seeds remain; the seven additions close deterministic
handoff/context coverage. An episode is one case even when it has several turns.

[Harness operations](harness.md) documents commands, versioned records,
accounting, blind pairing and Phase 2 prerequisites. That Phase 1 performed no
paid calls. The dated partial-execution amendment records the later OpenAI
smoke; comparative, complete operational and human-review gates remain pending.

Ticket 07 supplies these synthetic Intent cases as a stable input set. They are
not a model-quality report and contain no real Customer data. Phase 1 uses
oracle proposals to verify their multi-intent schema. Model detection quality
remains Phase 2 work.

Ticket 08 adds a separate synthetic persona seed. Its naturalness checks are rubrics for Ticket 12, not claimed unit-test proof.

Ticket 09 adds `grounding-cases.yaml`: now 13 synthetic grounding, uncertainty,
technical-risk, and mandatory-policy cases. The `facts` entries are fixture
overrides, not deployable Salon Knowledge. `tests/test_grounded_reply.py`
executes their deterministic proposal → rendering contract with synthetic
approval metadata. Live model quality, naturalness, token/cost/latency and
repeat-run prohibited-claim scoring remain Ticket 12; these unit cases are not
a live provider eval or a real smoke report.

Ticket 10 adds deterministic SQLite/webhook handoff lifecycle tests in
`tests/test_human_handoff.py`: activation, suppression, replay, release,
rollback, concurrency, and submission fencing. These tests do not replace the
real-model handoff detection/confirmation quality gate owned by Ticket 12.

Ticket 11 adds `appointment-interest-cases.yaml`: 13 synthetic episodes covering
complete/missing details, Professional preference, short answers, change,
cancellation, rescheduling, exhausted clarifications, invented slot values and
model/Customer attempts to confirm availability or booking. Their deterministic
policy contract runs in `tests/test_appointment_intake.py`. Ticket 12 must score
live-model extraction, naturalness and trust-boundary behavior with the same
expected outcomes; no model gate has been executed here.

`handoff-cases.yaml` exercises risk, human request, serious complaint, restart,
suppression and explicit release through isolated SQLite stores.
`context-cases.yaml` exercises bounded history, return after 31 days and exclusion
of pending assistant speech. Context references/topic changes are not proven by
these deterministic cases; existing incomplete-context/short-answer seeds must
receive repeated model evaluation in Phase 2.
