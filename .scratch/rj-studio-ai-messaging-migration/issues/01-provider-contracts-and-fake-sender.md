# 01: Separate provider ingress acknowledgement from outbound submission

**Status:** ready-for-agent

## Objective

Introduce the smallest provider-neutral interfaces needed to acknowledge an
inbound webhook independently from submitting an outbound Message. Preserve the
current Twilio/TwiML behavior during this ticket.

## Invariants

- Twilio details do not enter application or domain logic.
- HTTP acknowledgement is not an AI Reply or Outbound Delivery.
- Provider SDK values do not cross the provider seam.
- Existing webhook behavior, idempotency, deadlines, and persistence remain unchanged.

## Dependencies

- V1 baseline `d4a104f`.
- ADR 0006.

## Exact scope

- Split inbound authentication/parsing/acknowledgement from outbound submission contracts.
- Define canonical inbound and delivery-status event shapes needed by later tickets without implementing status persistence.
- Define canonical outbound request and accepted/retryable/permanent/unknown results.
- Add a deterministic fake outbound sender with call recording and programmable outcomes.
- Adapt current Twilio code to the inbound contract while retaining non-empty TwiML delivery.
- Keep interfaces narrow; do not create a provider registry or integration framework.

## Out of scope

- Database changes, executors, REST sending, status callbacks, Meta, early ACK, or behavior changes.

## Migrations

- None.

## Required tests

- Provider-contract tests for valid/invalid Twilio inbound parsing and acknowledgement.
- Fake sender tests for accepted, retryable, permanent, and unknown outcomes.
- Regression tests proving the current FastAPI webhook still returns the same TwiML and makes no outbound sender call.
- Type/static checks prove provider payload/SDK types do not enter canonical contracts.

## Crash cases

- No new crash window is introduced because the sender is not wired to runtime.
- Existing crash/retry tests must remain green.

## Definition of Done

- Contracts and fake are documented through their observable interface.
- Existing external behavior and full suite remain green.
- No production outbound request can occur.

## Rollout and rollback

- Safe to deploy because the new outbound seam is dormant.
- Rollback is code-only; no schema or persisted state changes exist.
