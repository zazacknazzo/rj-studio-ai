# 06: Add the Meta WhatsApp Cloud API production adapter

**Status:** ready-for-agent

## Objective

Implement Meta WhatsApp Cloud API as the production inbound, outbound, and
status adapter without changing application/domain orchestration.

## Invariants

- Meta payloads and SDK/HTTP types remain inside the adapter.
- Inbound `wamid` is the provider idempotency key.
- `phone_number_id` is persisted as the outbound channel identifier.
- A successful `/messages` response is Provider Acceptance, not delivered/read.
- Unknown outcomes receive no automatic retry.
- Channel eligibility policy is deterministic and precedes outbound submission.

## Dependencies

- 01: Provider contracts.
- 02: SQLite durability gate.
- 03: Durable outbox.
- 04: Proven proactive outbound lifecycle.
- 05: Async ingress and processing.

## Exact scope

- Implement Meta webhook verification, signature/authentication, batch parsing, and acknowledgement.
- Normalize inbound text Messages and sent/delivered/read/failed statuses.
- Commit every supported event in an authenticated valid batch before ACK. An unsupported event type is safely ignored or quarantined without discarding supported siblings; an invalid envelope/signature fails the whole request before persistence.
- Submit text through `/{phone-number-id}/messages` and persist returned `wamid`.
- Handle duplicate/batched inbound and status events idempotently.
- Add a narrow channel-policy seam for customer-service-window and template eligibility before send.
- Fail closed when a free-form reply is not eligible. Expose safe recovery/handoff state; do not invent or auto-select marketing content.
- Add configuration/readiness checks without making readiness call Meta externally.
- Keep Twilio available as the development adapter through the same contracts.

## Out of scope

- Full template authoring/approval workflow, campaigns, media, interactive Messages, CRM, Meta business onboarding UI, provider failover, or multi-number/multi-business administration.

## Migrations

- Add only routing/status fields not already covered by Ticket 03. Migration fixtures must preserve Twilio rows and never reinterpret their provider IDs.

## Required tests

- Official-contract fixtures for verification, signature failure, single/batched inbound, duplicate `wamid`, mixed supported/unsupported batch, invalid envelope, and statuses.
- Sender tests for accepted `wamid`, definitive retryable/permanent errors, and ambiguous network result.
- Customer-service-window/template gating tests that fail closed without invoking the sender.
- Duplicate/out-of-order status merge and accepted-then-failed blocking.
- Provider-contract parity with Twilio and no provider types in application/domain.
- Sanitized real Meta smoke test records date, commit, expected/observed result, inbound persistence, Provider Acceptance, and status evidence.

## Crash cases

- Crash before batch commit: no ACK; Meta retries the batch.
- Crash after commit before ACK: duplicate batch dedupes by `wamid`/status evidence.
- Crash after `/messages` may have accepted but before local commit: unknown; no automatic resend.
- Status callback before local finalization is merged or quarantined without losing stronger evidence.

## Definition of Done

- Meta handles ingress, text outbound, and statuses through existing canonical contracts.
- Channel policy prevents ineligible free-form submission.
- Real sanitized smoke passes without secrets or Customer PII in the repository.
- Full suite, migrations, Ruff, static checks, security review, and code review pass.

## Rollout and rollback

- Enable for a dedicated pilot channel only after Twilio path and recovery operations are stable.
- Preserve provider/channel routing on every durable delivery so rollback cannot send through the wrong adapter.
- Disable new acquisition before configuration rollback; pending/unknown Meta deliveries require explicit reconciliation and must never be replayed automatically through Twilio.
