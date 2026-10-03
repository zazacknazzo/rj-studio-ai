# Offline V1 harness — Ticket 12 Phase 1

This page documents the offline Phase 1 path. The separate, explicitly authorized
[partial OpenAI live collector](openai-partial-2026-10-02.md) records current
execution status, version-2 evidence, budgets and pending gates.

**Harness implemented / live model gate pending.** No live adapter, credentials,
network client, provider factory or production configuration is constructed.
The default is one repetition with deterministic fixture proposals. There is
no `live` command and no model switch in production.

## Operations

Run from the repository root, with the existing virtual environment:

```bash
.venv/bin/python -m rj_studio_ai.evaluation validate-suite
.venv/bin/python -m rj_studio_ai.evaluation dry-run --repetitions 1 --output /tmp/rj-eval-a.json
.venv/bin/python -m rj_studio_ai.evaluation validate-record /tmp/rj-eval-a.json
.venv/bin/python -m rj_studio_ai.evaluation report /tmp/rj-eval-a.json
.venv/bin/python -m rj_studio_ai.evaluation dry-run --repetitions 2 --output /tmp/rj-eval-b.json
.venv/bin/python -m rj_studio_ai.evaluation aggregate /tmp/rj-eval-a.json /tmp/rj-eval-b.json
```

Explicit repetitions are 1–100. Output files use exclusive creation; choose a
new path rather than overwriting evidence. Records and blind worksheets belong
outside Git. Validation failures print a fixed safe error code, never the input
or an exception that might echo secrets.

## Small implementation boundary

`evaluation/suite.py` loads the manifest and synthetic YAML cases.
`runner.py` uses the existing provider-neutral decision, trusted rendering,
persona, Conversation Context builder and MessageResponder/SQLite contracts.
Every episode gets an isolated temporary database, removed after execution.
It never loads runtime Salon Knowledge, `.env` or the application's database.
`records.py` validates evidence and recomputes metrics; `reporting.py` aggregates
populations and prepares pairs; `__main__.py` is the offline command boundary.

Grounding cases execute the proposal → trusted rendering seam; their handoff
flag is a proposal-stage check. Appointment/handoff episodes additionally
exercise durable completion, suppression and release. Context cases exercise
selection bounds and visibility. Intent cases feed oracle fixture Intents into
the schema: a pass proves orchestration/schema compatibility, **not** detection
accuracy. Persona checks cover deterministic surface/transparency rules;
warmth, fit and naturalness remain unscored human judgements.

## Availability and relevance in grounding fixtures

Both grounding paths supply `selected_facts` directly to the finalizer/model
context. The live `_SelectedKnowledgeContext` replaces the builder's Knowledge
with fixture-selected synthetic facts. This intentionally isolates grounding;
it does **not** evaluate production Knowledge selection or prove relevance.
Only selected facts whose meaning addresses the Message or unambiguous history
support a factual answer. Their detected factual Intents still require refs and
fact parts, including multi-intent coverage. Selection is not a render-all list.

The two injection variants separate these properties. The unnamed-Service case
deliberately makes corte's price available but not relevant; it permits safe
clarification/redirection and prohibits unsolicited facts. The explicit-corte
case requires its approved price while rejecting the injected value. The
multi-intent fixture now names corte explicitly too, without changing its
required price/hours coverage. No provider instruction or production rule changes.

Optional `expected.allowed_fact_ids` is an independent fixture relevance bound
on displayed approved facts: `[]` permits none; an omitted bound keeps the
existing oracle. Canonical statement presence in the final body identifies
displayed facts; unused reference declarations do not prove rendering. Unknown
selected IDs, duplicate or unselected allowed IDs and malformed bounds are
rejected at load time against the actual fixture definitions. Existing contains/excludes, authorized-text residue and
core validation still apply; this never authorizes free factual text. Applicable
mandatory policies must remain in the fixture's relevance bound.

`expected.handoff: null` means no fixed handoff outcome is required by that case.
It omits the handoff check from the case contract and metric denominator rather
than counting an unconditional pass. Other true/false handoff expectations stay
strict, including explicit-Service injection. Naturalness is recorded from human
review, not inferred from a semantic pass. Suite fingerprints change; historical
records, failure counts and responses are not rescored or rewritten. The current
ten-ID `SMOKE_CASES` paid plan is unchanged; the extra variant is offline-covered
and part of the 53-case suite. No new live execution is authorized at this step.

## Record v1

[run-record.schema.json](run-record.schema.json) is the generated JSON Schema.
Pydantic additionally enforces cross-field invariants that JSON Schema alone
cannot express. Records contain:

- run/suite IDs, timestamp with timezone, code revision, status, repetitions,
  case count and source/knowledge/prompt hashes;
- provider/model and explicit thinking, structured-output and token/context
  budgets (model names are opaque configuration, not availability claims);
- exact case/check contracts, critical flags, and one sample per case/repetition/
  turn; missing, duplicate, extra or omitted critical checks invalidate a record;
- safe per-attempt outcome/error code, billing classification, tokens and model
  latency; nullable usage means unknown, never zero by inference;
- per-execution E2E timing and optional ingress/queue/processing/outbound timings;
- status, reply hash and check verdicts, without Message bodies/provider IDs;
- pricing snapshot, independently recomputed summary and pending human-review
  rubric version.

`completed` samples count persisted logical AI Replies in episode runs;
`observed` samples test rendering/schema/context without pretending an AI Reply
was persisted. Suppressed/failed samples do not enter that reply denominator.
Run `completed` means all checks executed, not all checks passed.
An `incomplete` run must retain missing evaluations as `not_run`; critical
`not_run` fails closed. Report/validate-record binds contracts and hashes to the
checked-in suite, so editing a record cannot silently drop critical cases.

`live_import` is a record format reserved for later collection, not a callable
provider path. It rejects a deterministic provider, retains pending human
review and never awards overall V1/production approval. The operator still
must establish the completeness and authenticity of imported evidence.

## Metrics and accounting

- Counts/percentages always carry numerator, denominator and run count.
  Critical failures count failed or unexecuted **critical checks per turn and
  repetition** over all critical checks. Grounding/Intent/handoff/persona/context
  success uses passed checks over all applicable checks, including `not_run`.
  These offline contract scores are not probabilistic model-quality estimates.
- Model p50/p95 uses **all attempts**, including failed and paid retry attempts.
  Diagnostic E2E p50/p95 uses all recorded executions. **Billable E2E p50/p95**
  uses executions with at least one billable attempt, including failed executions,
  and is the latency-gate population. Zero-attempt suppressed/context samples
  cannot dilute that gate. Percentiles use R7 linear interpolation
  at `(n - 1) * p`; empty populations remain null. Aggregation recomputes from
  samples, never averages percentiles or individual cost-per-reply ratios.
- Tokens sum every attempt. Any missing usage makes the corresponding total
  unknown. `billable_retries` counts billable attempt numbers above 1 per
  execution. Token-consuming failures are explicit even without a completed
  reply; unknown billing/usage blocks a cost claim.
- Cost is the sum of each billable attempt's input/output tokens times its
  versioned rates. Cost per 1,000 is `total_cost * 1000 / completed_replies`.
  Paid failures/retries contribute to the numerator, never another completed
  reply. Zero completed replies yields null. Arithmetic uses Decimal before
  conversion to the JSON/report value.
- Offline fake-seam timings are labelled `offline_policy`; they are not actual
  LLM or WhatsApp latency. Live E2E starts at inbound persistence and ends at
  Provider Acceptance (or failure end), including queue wait/retries/outbound;
  ingress is separate. Model time alone cannot pass the 8-second gate. Missing
  E2E evidence or omission of attempt time leaves the gate pending/invalid.
- Deterministic/synthetic records always leave latency/cost `pending_live`.
  Live imported metric thresholds are p95 ≤8 seconds and ≤US$10/1,000 completed
  replies. No overall gate is awarded while naturalness/live review is pending.
  All billable eval/smoke executions must be enrolled, not a selected subset.

## Pricing and later provider configuration

`pricing.template.json` is unapproved with null rates; it is not a current price
table. Rates are USD per million input/output tokens, tied to exact provider/
model/version/source. Approved pricing requires an HTTPS source, review date
and neutral approving identifier. Missing/unapproved pricing or missing billed
  usage prevents cost/gate claims. Synthetic rates exist only in tests.
Standard text-token pricing is the initial supported contract; caching,
special billing tiers or additional charges require explicit verified accounting
before claiming their cost gate. Do not silently apply a standard rate to an
unsupported billing mode.

The current production GenerationMetric persists each attempt in SQLite with
provider/model/configuration, input/output/total tokens, latency, cost in
microusd, outcome and safe error code. It does not itself prove reply completion,
data population completeness or versioned pricing. Phase 2 must map those
attempts once, retain token-consuming failures/retries, and link completion and
inbound-persistence-to-acceptance timings without exporting Message bodies/SIDs.

The approved spec still names Sonnet 5 primary and GPT-5.6 Terra challenger.
Those names/API model IDs, availability, output/thinking configuration and
pricing sources are **unverified/staleness questions for Phase 2**. This change
does not rename the spec, choose a winner or change runtime provider selection.

## Paired, blind naturalness review

```bash
.venv/bin/python -m rj_studio_ai.evaluation compare /tmp/rj-eval-a.json /tmp/rj-eval-b.json --blind-sheet /tmp/rj-eval-blind.json
```

Comparison requires equal repetitions, code revision, suite/knowledge/prompt
hashes and budgets/configuration except provider/model. Use equal repetitions
for the example above (the 1-vs-2 example intentionally fails comparison).
Each pair shares case/repetition/turn. `naturalness-rubric.yaml` defines four
ordinal 1–5 dimensions plus A/B/tie preference. The worksheet randomizes A/B and
contains only IDs/hashes and empty score slots. The command's separate report
contains the operator mapping: **never give that report to the reviewer**.
The operator supplies matching sanitized answer excerpts by hash in a separate
private review packet; records contain no answer/customer transcript.
Identical answers may tie; missing/suppressed answers must remain explicit.
No human comparison is run here. Rating ingestion/gate approval remains Phase 2.

## Privacy and Phase 2 checklist

Strict record allowlists forbid extra transcript/credential/customer fields.
Fixtures require explicit `source_type: synthetic`; unknown Customer metadata,
phone/email/token patterns and recognized credentials are rejected. Regex is
defense in depth: it cannot identify every arbitrary human name or prove that
someone did not falsely label real data synthetic. Human source review remains
required. Digests permit reproducibility without storing bodies, but are not
anonymization permission for real Customer data. Never commit raw runs/packets.

Before separately authorized Phase 2:

1. Confirm actual provider/model IDs, structured-output/thinking settings and
   source-versioned approved pricing; define primary/challenger configurations.
2. Add only authorized live collection with explicit paid-call opt-in/limits;
   retain every billable attempt, failure, retry and completed-reply linkage.
3. Ensure equivalent synthetic inputs, prompt/knowledge snapshots, budgets and
   meaningful repetitions. Extend semantic context/topic-change assertions.
4. Collect real E2E populations, costs and uncertainty around sparse p95
   estimates; include smoke attempts and audit missing usage honestly.
5. Produce blind answer packets, execute human rubric review, audit zero critical
   outcomes, then decide gates/winner with evidence. Ticket 12 stays in-progress.

Meta smoke remains independently blocked on App Secret; this harness neither
reads credentials nor runs that smoke.
