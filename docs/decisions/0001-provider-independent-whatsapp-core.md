# Keep the WhatsApp core independent from the provider

Status: amended by ADR 0006

Provider-specific webhook parsing, verification, acknowledgement, and reply delivery belong behind a small `WhatsAppProvider` interface. V0 uses Twilio Sandbox; Meta Cloud API should be addable without rewriting Conversation persistence or application behavior.

V0.1 completed this seam. FastAPI passes a raw provider-neutral HTTP value to `TwilioProvider`; the adapter validates and translates it into a canonical `InboundMessage`. The application returns a canonical `AutomaticReply`, which the adapter renders as TwiML.

That TwiML response path remains the historical V0.1 implementation. ADR 0006
separates provider acknowledgement from proactive outbound submission: inbound
adapters translate and acknowledge webhooks, while outbound sender adapters
submit durable deliveries. The provider-independent intent of this record is
unchanged; its original single `WhatsAppProvider` shape is not the target seam.
