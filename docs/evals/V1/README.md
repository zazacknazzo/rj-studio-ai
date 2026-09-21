# V1 eval seed

Ticket 07 supplies these synthetic Intent cases as a stable input set. They are
not a model-quality report and contain no real Customer data. Ticket 12 owns
runnable model evaluation, repeated runs, scoring, comparison, and gate records.

Ticket 08 adds a separate synthetic persona seed. Its naturalness checks are rubrics for Ticket 12, not claimed unit-test proof.

Ticket 09 adds deterministic grounding cases for canonical critical facts,
unknown facts, false Customer claims, prompt injection, unavailable scheduling,
technical risk, mandatory policy, and Human Handoff overrides. These remain
synthetic inputs and expected safety properties; Ticket 12 owns model runs and
scored reports.
