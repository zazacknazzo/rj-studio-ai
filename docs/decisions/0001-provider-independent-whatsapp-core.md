# Keep the WhatsApp core independent from the provider

Status: accepted

Provider-specific webhook parsing, verification, acknowledgement, and reply delivery belong behind a small `WhatsAppProvider` interface. V0 uses Twilio Sandbox; Meta Cloud API should be addable without rewriting Conversation persistence or application behavior.

The V0 audit found that form parsing still leaks into the HTTP route. This is tracked as pre-V1 debt in `../ARCHITECTURE.md` and does not change the decision.
