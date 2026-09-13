# 01: Deliver the Sandbox Conversation flow

**What to build:** A Customer sends a Twilio Sandbox Message, RJ Studio AI persists the inbound and outbound Messages, and Twilio receives an Automatic Reply through the provider-independent webhook flow.

**Blocked by:** None (can start immediately).

**Status:** done

- [x] Health and webhook endpoints run through FastAPI.
- [x] The webhook flow uses `WhatsAppProvider`, not Twilio-specific application logic.
- [x] SQLite stores the Conversation and both Message directions.
- [x] Repeated delivery of one Twilio Message does not duplicate persisted Messages.
- [x] HTTP-level tests prove the behavior.
