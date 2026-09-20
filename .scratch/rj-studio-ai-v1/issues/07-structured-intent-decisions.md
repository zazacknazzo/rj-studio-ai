# 07: Produce validated Intent decisions

**What to build:** Lívia can turn a bounded request into one validated structured decision with multiple Intents, uncertainty, knowledge references, critical factual claims, and a proposed Human Handoff outcome.

**Blocked by:** 02: Deliver ordered, deadline-bound webhook generation; 05: Load approved Salon Knowledge; 06: Build bounded Conversation Context.

**Status:** in-progress

## Context

The structured decision is a contract for application code, not a source of truth. Its LLM-generated references, factual claims, and `handoff=false` value remain untrusted proposals.

## Likely components

LLM structured decision schema, provider translation, application validation boundary, Intent vocabulary, FastAPI safe-failure path, and synthetic eval cases.

## Acceptance criteria

- [ ] The decision supports the approved Intent catalog, including multiple Intents, and carries reply text, categorical uncertainty, allowed knowledge references, structured critical claims, handoff proposal, and reason.
- [ ] Availability can be classified as appointment-related without claiming real availability.
- [ ] Unsupported Intent, missing field, schema-invalid output, or invalid reference never becomes an AI Reply and follows the safe failure path.
- [ ] The application treats all LLM decision fields as proposals pending trusted validation in the grounding and handoff tickets.

## Required tests

- [ ] Provider-contract and FastAPI tests cover valid single/multiple Intent decisions, appointment-related intent, invalid schema, unknown Intent, and missing required fields.
- [ ] Synthetic Intent eval cases cover greeting, price, professional, hours, location, technical guidance, appointment, complaint, promotion, human request, and other.

## Non-goals

- Separate generic classifier, chain-of-thought capture, lead scoring, next-best-action, or trusting model output as factual policy.
