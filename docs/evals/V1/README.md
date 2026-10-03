# V1 eval suite

Latest authorized step: [shared multi-intent instruction and controlled retest](multi-intent-instruction-correction-2026-10-03.md).

Targeted follow-up: [multi-fact handoff diagnosis](multiple-facts-diagnostic-2026-10-02.md).

Current execution amendment: [512-token OpenAI evaluation](openai-smoke-512-2026-10-02.md).
Historical diagnostic run: [200-token partial evaluation](openai-partial-2026-10-02.md).
Anthropic comparison is deferred by the product owner. Ticket 12 remains
in-progress; comparative acceptance and human review are not complete.

Ticket 12 Phase 1: **harness implemented / live model gate pending**.
`suite.yaml` indexes **52 synthetic cases**: 14 Intent, 6 persona, 12 grounding,
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

Ticket 09 adds `grounding-cases.yaml`: 12 synthetic grounding, uncertainty,
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
