# Architecture Decision Records

Read an ADR only when a task touches its decision.

| ADR | Decision |
| --- | --- |
| [0001](0001-provider-independent-whatsapp-core.md) | Keep WhatsApp application behavior independent from Twilio |
| [0002](0002-single-business-before-saas.md) | Prove RJ Studio through V6 before building SaaS infrastructure |
| [0003](0003-durable-webhook-idempotency.md) | Prepare one durable reply per provider Message and replay it on retries |
| [0004](0004-message-retention.md) | Retain raw Messages for 90 days and purge only through explicit maintenance |

Add an ADR only for a hard-to-reverse choice that would be surprising without its trade-off. Keep it concise and update this index.
