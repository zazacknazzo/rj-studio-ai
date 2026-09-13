# Keep the WhatsApp core independent from the provider

Status: accepted

Provider-specific webhook parsing, verification, acknowledgement, and reply delivery belong behind a small `WhatsAppProvider` interface. V0 uses Twilio Sandbox; Meta Cloud API should be addable without rewriting Conversation persistence or application behavior.

V0.1 completed this seam. FastAPI passes a raw provider-neutral HTTP value to `TwilioProvider`; the adapter validates and translates it into a canonical `InboundMessage`. The application returns a canonical `AutomaticReply`, which the adapter renders as TwiML.
