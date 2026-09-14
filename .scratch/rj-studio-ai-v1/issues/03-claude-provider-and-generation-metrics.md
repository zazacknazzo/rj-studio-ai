# 03: Add the Claude provider and generation metrics

**What to build:** The safe generated-reply path can use Claude Sonnet 5 through a narrow provider adapter, persist privacy-safe call metrics, and retain the deterministic fake for normal tests.

**Blocked by:** 02: Deliver ordered, deadline-bound webhook generation.

**Status:** ready-for-agent

## Context

Claude Sonnet 5 is V1’s production model. GPT-5.6 Terra is an eval-only challenger, so production fallback is explicitly excluded.

## Likely components

LLM provider contract, Claude adapter and configuration, generation metric persistence, application composition, provider-contract tests, and environment documentation.

## Acceptance criteria

- [ ] Claude Sonnet 5 is selectable as the production provider with thinking explicitly disabled and structured output used where applicable.
- [ ] Provider timeout, transient error, and malformed structured response enter the V1 safe failure path; no automatic Claude-to-Terra fallback exists.
- [ ] Every provider attempt records model, configuration, latency, input/output tokens, estimated cost, outcome, and safe error code without full Message bodies, phone numbers, provider identifiers, secrets, or chain-of-thought.
- [ ] The deterministic LLM fake remains the default for ordinary automated tests and can assert call count and supplied context.

## Required tests

- [ ] Provider-contract tests for request configuration, structured-response translation, timeout, transient failure, and malformed output.
- [ ] FastAPI and SQLite tests for metric persistence and redaction on success and failure.
- [ ] Configuration tests prove missing required LLM settings fail safely.

## Non-goals

- GPT-5.6 Terra production routing, automatic model switching, full eval suite, external observability platform, or logging full prompts/messages.
