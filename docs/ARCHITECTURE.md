# Architecture

This document describes code that exists at V0. Future constraints are labeled separately; planned roadmap capabilities are not presented as implemented modules.

## V0 runtime flow

```text
Twilio Sandbox
  → POST /webhooks/whatsapp
  → FastAPI composition and HTTP handling
  → MessageResponder
      → WhatsAppProvider / TwilioProvider
      → SqliteConversationStore
  → TwiML response
```

An accepted webhook becomes an `InboundMessage`. `MessageResponder` records the inbound Message and fixed Automatic Reply, then asks the provider for the HTTP response. A repeated Twilio `MessageSid` receives an empty acknowledgement and creates no additional Message rows.

## Existing modules

| Module | Current responsibility | Interface or seam |
| --- | --- | --- |
| `config.py` | Loads `.env` settings | `Settings` |
| `main.py` | Builds FastAPI, wires dependencies, exposes health and webhook routes | HTTP seam through `create_app()` |
| `application.py` | Coordinates one inbound Message, persistence, deduplication, and reply | `MessageResponder.handle()` |
| `domain.py` | Carries shared Message and webhook values; `WebhookInput` is still form-shaped | Dataclasses |
| `persistence.py` | Creates and accesses the SQLite schema | `SqliteConversationStore` |
| `providers/base.py` | Defines provider behavior and provider errors | `WhatsAppProvider` |
| `providers/twilio.py` | Validates Twilio signatures, translates form fields, and builds TwiML | `TwilioProvider` adapter |

## Current data model

SQLite contains:

- `conversations`: one row per `(provider, customer_address)` with creation and update timestamps.
- `messages`: ordered inbound and outbound rows linked to a Conversation.
- `(provider, provider_message_id)` is unique, providing inbound webhook deduplication.

There is no `tenant_id`, Customer profile, semantic memory, model trace, Appointment, or attribution data in V0.

## Dependency and seam decisions

- FastAPI is the composition root and the highest automated test seam.
- Twilio is a true external dependency, so `WhatsAppProvider` is a justified seam. Meta Cloud API must become another adapter.
- SQLite is local and directly testable with temporary databases. A generic persistence interface is deferred until a second implementation or V1 behavior creates real variation.
- RJ Studio rules will belong in localized knowledge or policy modules when those capabilities are specified. They must not enter generic Conversation orchestration.

See `decisions/0001-provider-independent-whatsapp-core.md` and `decisions/0002-single-business-before-saas.md`.

## V0 debt before V1

These are audit findings, not implemented V1 design:

1. **Make reply retries truthful and recoverable.** The store records an outbound Message before Twilio receives the TwiML. A failure after the commit can leave history claiming a reply was sent while a retry receives an empty acknowledgement. Persist a stable response per inbound Message and define retry/delivery states before replies become non-deterministic or expensive.
2. **Finish the provider seam.** The HTTP route currently parses form data and uses `twilio_public_webhook_url`; `WebhookInput` also assumes form fields. Move provider-specific request parsing behind the adapter, or pass a protocol-neutral raw request, before the seam is extended.
3. **Introduce minimal schema migrations.** V0 only runs `CREATE TABLE IF NOT EXISTS`. Add a small versioned migration mechanism before V1 changes persistence.
4. **Separate liveness from readiness.** `/health` returns success even when signature validation is active with no Twilio token. Readiness should verify required configuration and writable persistence. Record one real Sandbox smoke test.
5. **Remove database creation during import.** Importing `rj_studio_ai.main` creates the default SQLite file. Move initialization into application lifecycle or explicit composition so agent checks and tests have no unexpected workspace side effects.
6. **Set a minimum data policy.** Before V1 stores richer Conversation context, decide retention and deletion rules for WhatsApp addresses and Message content. Do not invent this policy in code.
7. **Lock down critical failure paths.** Add coverage for malformed callbacks returning HTTP 400 and for concurrent delivery of the same provider Message before relying on deduplication around an LLM call.

The duplicate webhook path also advances `conversations.updated_at` before duplicate detection. Correct it with the retry work.

## Work that can stay inside V1 slices

- Limit Conversation history by an explicit token/message budget and add the needed SQLite index.
- Introduce a narrow persistence port only when V1 needs context retrieval or a test adapter.
- Define LLM timeout, fallback, retry, and failure logging with the first LLM slice.

## Deliberately deferred

- Multi-tenant tables, routing, configuration, and administration.
- Replacing SQLite based only on hypothetical scale.
- Generic integration frameworks beyond concrete provider needs.
- Cross-provider Customer identity until the Meta or CRM slice requires it.
- Full observability, retention, and privacy systems before their roadmap slice, except safeguards required by the data already stored.
- Test dependency deprecation warnings on Python 3.14; they are maintenance noise, not a V1 blocker.
