# Architecture

This document describes the runtime through V1 ticket 03. The webhook uses durable generation claims, per-Conversation ordering, one end-to-end deadline, and a narrow Claude adapter. The deterministic generator remains the normal test/local default. The passing V0.1 real Sandbox acceptance result is tracked separately in the smoke-test runbook.

## Current runtime flow

```text
Twilio Sandbox
  → POST /webhooks/twilio
  → start 10-second monotonic deadline
  → provider-neutral raw HTTP request
  → TwilioProvider authentication and translation
  → canonical InboundMessage
  → persist inbound without acquiring generation
  → acquire oldest eligible Message in its Conversation
  → FixedReplyGenerator or AnthropicReplyGenerator outside SQLite transaction
  → persist privacy-safe provider-attempt metric
  → atomically persist one reply and terminal processing state
  → canonical AIReply
  → TwilioProvider TwiML rendering
  → TwiML response
```

The legacy `POST /webhooks/whatsapp` route remains an alias. Both routes pass raw HTTP data to the adapter. A repeated Twilio `MessageSid` retrieves the exact AI Reply already stored and returns the same non-empty TwiML without another generation.

## Existing modules

| Module | Current responsibility | Interface or seam |
| --- | --- | --- |
| `config.py` | Loads `.env` settings | `Settings` |
| `main.py` | Builds FastAPI, wires dependencies, owns explicit startup, and exposes liveness, readiness, and webhook routes | HTTP seam through `create_app()` |
| `application.py` | Coordinates admission, Conversation ordering, bounded wait, deterministic generation retries, and durable completion | `MessageResponder.handle()` |
| `deadline.py` | Holds the single monotonic webhook deadline and finalization reserve | `ExecutionDeadline` |
| `domain.py` | Carries canonical inbound Message, AI Reply, and history values | Dataclasses |
| `generation.py` | Defines the narrow synchronous generation seam, result, failure, and metric values | `ReplyGenerator`, `GeneratedReply` |
| `providers/anthropic.py` | Translates the core generation contract to the official Anthropic SDK | `AnthropicReplyGenerator` |
| `persistence.py` | Provides transactional idempotency, durable generation claims, privacy-safe metrics, history, readiness writes, retention purge, and Conversation deletion | `SqliteConversationStore` |
| `migrations/` | Holds and applies ordered Alembic revisions | `MigrationManager` |
| `maintenance.py` | Exposes explicit migrate, purge, and Conversation-deletion commands | `rj-studio-maintenance` |
| `providers/base.py` | Defines provider behavior and provider errors | `WhatsAppProvider` |
| `providers/twilio.py` | Parses the raw form, validates the exact public URL and signature, translates Messages, and builds TwiML | `TwilioProvider` adapter |

## Current data model

SQLite contains:

- `conversations`: one row per `(provider, customer_address)` with creation and update timestamps.
- `messages`: ordered inbound and outbound rows linked to a Conversation.
- `(provider, provider_message_id)` is unique, providing inbound webhook deduplication.
- Each outbound reply points to its inbound Message through `in_reply_to_message_id`.
- A unique index on that link prevents a second logical reply for one inbound Message.
- `message_processing`: one durable lifecycle per inbound Message, with `processing`, `retryable`, `completed`, or terminal `suppressed` state.
- `generation_metrics`: one privacy-safe model-attempt record per inbound generation attempt; it contains no Message body, Customer address, provider Message identifier, key, or prompt.
- A processing claim has a unique owner token, a 30-second lease, and no more than two attempts. Database constraints protect state shape and the relationship between terminal state and reply presence.
- `alembic_version` records the current schema revision.

There is no `tenant_id`, Customer profile, semantic memory, model trace, Appointment, or attribution data in V0.

## Dependency and seam decisions

- FastAPI is the composition root and the highest automated test seam.
- Twilio is a true external dependency, so `WhatsAppProvider` is a justified seam. Meta Cloud API must become another adapter.
- SQLite is local and directly testable with temporary databases. A generic persistence interface is deferred until a second implementation or V1 behavior creates real variation.
- RJ Studio rules will belong in localized knowledge or policy modules when those capabilities are specified. They must not enter generic Conversation orchestration.
- `BEGIN IMMEDIATE`, the inbound uniqueness constraint, and the unique reply link make reply preparation correct across threads and process restarts. This does not assert exactly-once WhatsApp delivery.
- Claim acquisition and completion use separate short `BEGIN IMMEDIATE` transactions. This leaves the future LLM call outside a database transaction; only the current unexpired owner can finalize an AI Reply. After two failed or expired generation attempts, a dedicated finalization claim can acquire the same lifecycle without incrementing the attempt count, allowing a later slice to persist one deterministic safe reply without leaving the Message stranded.
- Claim acquisition checks earlier inbound Messages in the same Conversation. Any earlier non-terminal Message blocks a later claim, while claims for different Conversations hold no shared application lock. SQLite write transactions remain short and never span generation, wait, sleep, or backoff.
- A blocked webhook polls through separate short transactions for at most one second. If the predecessor remains non-terminal, the current inbound stays persisted and the webhook returns HTTP 503 without provider reply markup. A later provider retry can claim it after the predecessor becomes terminal.
- The webhook creates one 10-second monotonic deadline before reading and translating the inbound request. SQLite lock timeouts, ordering polls, retry backoff, generation, finalization, provider rendering, and response preparation all consume that same budget.
- One second of the total is reserved for final persistence and provider response rendering. New generation attempts require at least 100 milliseconds outside that reserve. These are local V1.1 operating constants, not model-specific timeout policy.
- Claude calls receive the existing remaining work budget as their SDK timeout and run inside an asynchronous cancellation scope using that same absolute budget; cleanup is not awaited after that budget has expired. They start only with at least one second available outside the finalization reserve. SDK retries are disabled; the durable application lifecycle owns the two-attempt limit. Claude Sonnet 5 uses `thinking={"type": "disabled"}` and a minimal JSON envelope containing only `reply_text`; Intent and business decisions remain deferred.
- Attempt metrics persist provider, returned model, non-secret configuration label, latency, available token counts, configured-price cost estimate, outcome, and safe error code. Pricing is supplied in environment configuration and is not hardcoded because provider pricing may change.
- Existing V0.1 inbound/reply pairs migrate to `completed` with zero LLM attempts. The current deterministic fixed-reply flow creates the same terminal lifecycle atomically with its AI Reply.
- Alembic owns schema versions. Application startup and the maintenance command invoke it explicitly; importing modules performs no database I/O.
- `/health` checks process liveness. `/ready` checks local configuration, schema revision, schema shape, and a rollback-only write transaction.
- Retention runs only through an operator command. No startup hook, scheduler, or webhook path deletes Messages.

See the focused records under `decisions/`, especially ADRs 0001, 0003, 0004, and 0005.

## V0.1 acceptance

The real Twilio Sandbox test passed with signature validation enabled on 2026-09-13. Twilio received one synthetic inbound Message, called the canonical webhook with HTTP 200, delivered the configured reply, and the fresh database contained exactly one linked inbound/outbound pair. See the [redacted execution record](runbooks/twilio-sandbox-smoke-test.md).

## Work that can stay inside V1 slices

- Limit Conversation history by an explicit token/message budget and add the needed SQLite index.
- Introduce a narrow persistence port only when V1 needs context retrieval or a test adapter.
- Bind the real provider timeout to `remaining_budget` and add privacy-safe attempt metrics with ticket 03.
- Decide whether reply-delivery status callbacks are needed when V1 failure handling is specified.

## Deliberately deferred

- Multi-tenant tables, routing, configuration, and administration.
- Replacing SQLite based only on hypothetical scale.
- Generic integration frameworks beyond concrete provider needs.
- Cross-provider Customer identity until the Meta or CRM slice requires it.
- Full observability and privacy systems before their roadmap slice.
- Automatic or scheduled retention; the V0.1 command remains operator initiated.
- Test dependency deprecation warnings on Python 3.14; they are maintenance noise, not a V1 blocker.
