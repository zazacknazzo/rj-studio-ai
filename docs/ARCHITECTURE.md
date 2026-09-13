# Architecture

This document describes the V0.1 code. The real Sandbox acceptance result is tracked separately in the smoke-test runbook. Planned roadmap capabilities are not presented as implemented modules.

## V0.1 runtime flow

```text
Twilio Sandbox
  → POST /webhooks/twilio
  → provider-neutral raw HTTP request
  → TwilioProvider authentication and translation
  → canonical InboundMessage
  → MessageResponder
  → SqliteConversationStore atomic get-or-create
  → canonical AutomaticReply
  → TwilioProvider TwiML rendering
  → TwiML response
```

The legacy `POST /webhooks/whatsapp` route remains an alias. Both routes pass raw HTTP data to the adapter. A repeated Twilio `MessageSid` retrieves the exact Automatic Reply already stored and returns the same non-empty TwiML.

## Existing modules

| Module | Current responsibility | Interface or seam |
| --- | --- | --- |
| `config.py` | Loads `.env` settings | `Settings` |
| `main.py` | Builds FastAPI, wires dependencies, owns explicit startup, and exposes liveness, readiness, and webhook routes | HTTP seam through `create_app()` |
| `application.py` | Selects or retrieves one durable Automatic Reply for a canonical inbound Message | `MessageResponder.handle()` |
| `domain.py` | Carries canonical inbound Message, Automatic Reply, and history values | Dataclasses |
| `persistence.py` | Provides transactional idempotency, history, readiness writes, retention purge, and Conversation deletion | `SqliteConversationStore` |
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
- `alembic_version` records the current schema revision.

There is no `tenant_id`, Customer profile, semantic memory, model trace, Appointment, or attribution data in V0.

## Dependency and seam decisions

- FastAPI is the composition root and the highest automated test seam.
- Twilio is a true external dependency, so `WhatsAppProvider` is a justified seam. Meta Cloud API must become another adapter.
- SQLite is local and directly testable with temporary databases. A generic persistence interface is deferred until a second implementation or V1 behavior creates real variation.
- RJ Studio rules will belong in localized knowledge or policy modules when those capabilities are specified. They must not enter generic Conversation orchestration.
- `BEGIN IMMEDIATE`, the inbound uniqueness constraint, and the unique reply link make reply preparation correct across threads and process restarts. This does not assert exactly-once WhatsApp delivery.
- Alembic owns schema versions. Application startup and the maintenance command invoke it explicitly; importing modules performs no database I/O.
- `/health` checks process liveness. `/ready` checks local configuration, schema revision, schema shape, and a rollback-only write transaction.
- Retention runs only through an operator command. No startup hook, scheduler, or webhook path deletes Messages.

See the focused records under `decisions/`, especially ADRs 0001, 0003, and 0004.

## Remaining acceptance before V1

- Run and record the real Twilio Sandbox smoke test with signature validation enabled.
- Keep the V0.1 spec at `approved` until that record passes.

## Work that can stay inside V1 slices

- Limit Conversation history by an explicit token/message budget and add the needed SQLite index.
- Introduce a narrow persistence port only when V1 needs context retrieval or a test adapter.
- Define LLM timeout, fallback, retry, and failure logging with the first LLM slice.
- Decide whether reply-delivery status callbacks are needed when V1 failure handling is specified.

## Deliberately deferred

- Multi-tenant tables, routing, configuration, and administration.
- Replacing SQLite based only on hypothetical scale.
- Generic integration frameworks beyond concrete provider needs.
- Cross-provider Customer identity until the Meta or CRM slice requires it.
- Full observability and privacy systems before their roadmap slice.
- Automatic or scheduled retention; the V0.1 command remains operator initiated.
- Test dependency deprecation warnings on Python 3.14; they are maintenance noise, not a V1 blocker.
