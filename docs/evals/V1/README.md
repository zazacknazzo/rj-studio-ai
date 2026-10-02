# V1 eval seed

Ticket 07 supplies these synthetic Intent cases as a stable input set. They are
not a model-quality report and contain no real Customer data. Ticket 12 owns
runnable model evaluation, repeated runs, scoring, comparison, and gate records.

Ticket 08 adds a separate synthetic persona seed. Its naturalness checks are rubrics for Ticket 12, not claimed unit-test proof.

Ticket 09 adds `grounding-cases.yaml`: 12 synthetic grounding, uncertainty,
technical-risk, and mandatory-policy cases. The `facts` entries are fixture
overrides, not deployable Salon Knowledge. `tests/test_grounded_reply.py`
executes their deterministic proposal → rendering contract with synthetic
approval metadata. Live model quality, naturalness, token/cost/latency and
repeat-run prohibited-claim scoring remain Ticket 12; these unit cases are not
a live provider eval or a real smoke report.
