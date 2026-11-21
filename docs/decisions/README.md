# Architecture Decision Records

Read an ADR only when a task touches its decision.

| ADR | Decision |
| --- | --- |
| [0001](0001-provider-independent-whatsapp-core.md) | Keep WhatsApp behavior provider-independent; amended by ADR 0006 |
| [0002](0002-single-business-before-saas.md) | Prove RJ Studio through V6 before building SaaS infrastructure |
| [0003](0003-durable-webhook-idempotency.md) | Preserve inbound/reply idempotency; amended by ADR 0006 |
| [0004](0004-message-retention.md) | Retain raw Messages for 90 days and purge only through explicit maintenance |
| [0005](0005-durable-llm-generation-claims.md) | Coordinate slow LLM generation; amended by ADR 0006 |
| [0006](0006-separate-messaging-ingress-processing-delivery.md) | Separate durable ingress, AI processing, and outbound delivery |
| [0007](0007-trusted-reply-rendering.md) | Render factual replies from approved statements and controlled conversational phrases |
| [0008](0008-durable-human-handoff.md) | Persist Conversation handoff atomically and fence delivery submission/manual release |
| [0009](0009-agentic-conversation-boundary.md) | **Proposed:** return conversational initiative to the model while retaining trusted fact/action/state authority; does not amend accepted ADRs |
| [0010](0010-operational-observation-journal.md) | Journal scoped operational observations independently of Messages and future effects |
| [0011](0011-operational-generation-pause.md) | Persist operational pause and fence generation independently of Human Handoff and outbound |
| [0012](0012-operational-outbound-pause.md) | Cancel proven-unsubmitted deliveries and fence authorization under operational pause |

Add an ADR only for a hard-to-reverse choice that would be surprising without its trade-off. Keep it concise and update this index.

- [0013](0013-authenticated-automation-operations.md): authenticated operations and future-only resume.
- [0016](0016-scoped-delivery-status-evidence.md): scoped delivery receipts and explicit success/failure conflicts for Telnyx.

- [0017: Durable channel lifecycle](0017-durable-channel-lifecycle.md) — explicit WABA binding, blocked defaults and replay-safe lifecycle effects.

- [0018: Eligibility and submission identity](0018-whatsapp-eligibility-and-submission-identity.md) — strict source-time window, separate consent and conservative retry evidence.

- [0019 — Deterministic offline Telnyx sender](0019-deterministic-offline-telnyx-sender.md)
