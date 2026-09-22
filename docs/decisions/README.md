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

Add an ADR only for a hard-to-reverse choice that would be surprising without its trade-off. Keep it concise and update this index.
