# RJ Studio AI V0

**Status:** implemented

## Problem Statement

RJ Studio needs a safe first version of WhatsApp automation that can receive a Sandbox message, persist the Conversation, and send an Automatic Reply. The first provider is Twilio, but the product must be able to move to Meta Cloud API later without rebuilding its core flow.

## Solution

Create a Python FastAPI backend with one WhatsApp webhook. A Twilio adapter verifies and translates incoming Sandbox requests into provider-independent Messages, while the application persists the Conversation and asks the adapter to return the Automatic Reply. Runtime values come from a `.env` file.

## User Stories

1. As a Customer, I want my WhatsApp Message to reach RJ Studio AI, so that I receive an immediate response.
2. As a Customer, I want one Automatic Reply for each accepted Message, so that I know RJ Studio received it.
3. As the salon owner, I want inbound and outbound Messages saved, so that a Conversation has a minimal history.
4. As the salon owner, I want repeated webhook delivery handled without duplicating persisted inbound Messages, so that retry behavior does not corrupt history.
5. As the operator, I want the Automatic Reply configured through environment values, so that I can change copy without editing code.
6. As the operator, I want the database location configured through environment values, so that local and hosted environments can differ.
7. As the operator, I want Twilio signature verification enabled for real callbacks, so that forged requests are rejected.
8. As the developer, I want signature verification switchable in local tests, so that the flow can be exercised without real credentials.
9. As the developer, I want provider behavior isolated behind one interface, so that Meta Cloud API can be added as another adapter.
10. As the developer, I want a health endpoint, so that I can tell whether the backend is running.
11. As the developer, I want setup and Sandbox instructions, so that I can connect Twilio without guessing paths or settings.
12. As the developer, I want tests at the HTTP seam, so that the full observable V0 behavior survives internal refactoring.

## Implementation Decisions

- FastAPI owns the HTTP application and exposes health and WhatsApp webhook routes.
- `WhatsAppProvider` is the external seam for verification, inbound Message translation, reply delivery, and webhook acknowledgement.
- `TwilioProvider` is the only V0 adapter and uses Twilio's supported request validation and TwiML utilities.
- The application flow depends on the provider interface and the Conversation store, not on Twilio-specific request fields.
- SQLite provides minimal durable persistence for Conversations and their inbound and outbound Messages.
- A provider message identifier makes inbound persistence idempotent when Twilio retries a webhook.
- Pydantic settings load `.env` values, including reply text, database path, public webhook URL, and signature validation.
- The public webhook URL may be configured because Twilio signature verification must use the externally visible URL when a tunnel or proxy is involved.
- V0 returns a fixed Automatic Reply. There is no AI decision-making.

## Testing Decisions

- The primary seam is the FastAPI HTTP interface exercised with a test client and a temporary SQLite database.
- Tests assert observable status codes, TwiML response content, retry idempotency, persisted history exposed through the application store, and rejection of invalid signatures.
- Provider configuration is injected through the application factory; tests do not mock internal modules.
- Twilio is treated as a system boundary. Signature generation uses Twilio's supported validator rather than reimplementing its algorithm.

## Out of Scope

- Generative AI or intent classification
- CRM workflows or a management interface
- Trinks integration
- Google Ads integration
- Meta Cloud API implementation
- Proactive outbound campaigns, templates, media, or human handoff
- Production hosting and observability infrastructure

## Further Notes

The V0 must run locally and be connectable to Twilio Sandbox through an HTTPS tunnel. The same core flow should accept a future Meta adapter without changes to Conversation persistence.
