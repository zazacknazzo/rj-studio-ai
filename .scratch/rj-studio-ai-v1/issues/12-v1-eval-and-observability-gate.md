# 12: Run the V1 eval and observability gate

**What to build:** V1 has a reproducible, privacy-safe evaluation record and Sonnet-versus-Terra comparison that can decide whether the completed AI Attendant meets its safety, quality, latency, and cost gates.

**Blocked by:** 03: Add the Claude provider and generation metrics; 04: Recover pending generated Messages explicitly; 05: Load approved Salon Knowledge; 06: Build bounded Conversation Context; 07: Produce validated Intent decisions; 08: Apply Lívia’s stable WhatsApp persona; 09: Enforce grounded factual replies and trusted overrides; 10: Make Human Handoff durable and atomic; 11: Collect appointment interest before handoff.

**Status:** ready-for-agent

## Context

Evals complement deterministic webhook, SQLite, migration, and provider-contract tests. All cases must be synthetic or explicitly sanitized.

## Likely components

V1 eval case index and run records, eval runner/reporting, metric aggregation, model-comparison execution, and deterministic report validation tests.

## Acceptance criteria

- [ ] The suite contains at least 28 synthetic or sanitized cases spanning grounding, hallucination, Intent, context, persona, uncertainty, prompt injection, technical risk, appointment behavior, and Human Handoff.
- [ ] Every run records case/run counts, model/configuration, critical failures, grounding, Intent, handoff, persona/naturalness, p50/p95 latency, input/output tokens, and estimated cost without full Message bodies, secrets, or unnecessary PII.
- [ ] Critical grounding and Human Handoff cases have zero prohibited claims; percentages name numerator, denominator, and run count.
- [ ] Sonnet and Terra are compared with equivalent input, knowledge, prompt, token budget, and configuration; important probabilistic cases run repeatedly and naturalness review is paired and preferably blind.
- [ ] The operational gates use every billable eval/smoke execution, including paid retries and token-consuming failures: p95 end-to-end latency is at most 8 seconds and estimated cost is at most US$10 per 1,000 completed AI Replies, unless an explicit evidence-backed threshold revision is recorded.

## Required tests

- [ ] Deterministic tests reject invalid run records, unreported critical failure, real Customer fixture, missing denominator, and metric redaction failure.
- [ ] Tests verify failed/retried paid attempts remain in latency/cost accounting and do not inflate the completed-reply denominator.

## Non-goals

- Automatic model switching, production alerting platform, external provider failover, real Customer conversations in fixtures, or authorization for autonomous production operation.
