# 01: Deliver the Sandbox Conversation flow

**What to build:** A Customer sends a Twilio Sandbox Message, RJ Studio AI persists the inbound and outbound Messages, and Twilio receives an Automatic Reply through the provider-independent webhook flow.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Health and webhook endpoints run through FastAPI.
- [ ] The webhook flow uses `WhatsAppProvider`, not Twilio-specific application logic.
- [ ] SQLite stores the Conversation and both Message directions.
- [ ] Repeated delivery of one Twilio Message does not duplicate persisted Messages.
- [ ] HTTP-level tests prove the behavior.
