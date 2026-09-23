# Twilio proactive outbound smoke test

Status: pending operational gate

This runbook validates Messaging Migration 04 against the real Twilio WhatsApp
Sandbox. Use a fresh ignored database and synthetic content. Never record API
secrets, Auth Tokens, complete phone numbers, tunnel credentials, MessageSid, or
Customer content.

## Prerequisites

- A WhatsApp account joined to the Twilio Sandbox.
- Twilio Account SID plus a dedicated API key SID and secret.
- Twilio Auth Token for webhook signature validation.
- One HTTPS tunnel forwarding to the application.
- `DELIVERY_MODE=proactive` and `APP_PROCESS_COUNT=1`.
- Public URLs ending in `/webhooks/twilio` and `/webhooks/twilio/status`.
- A fresh ignored database such as `work/smoke/m04.db`.

## Steps

1. Configure the proactive environment and migrate the fresh database.
2. Start one Uvicorn process and the HTTPS tunnel.
3. Configure the Sandbox inbound webhook and the exact public URLs.
4. Confirm `/health` and `/ready` return HTTP 200, including the executor check.
5. Send one synthetic inbound Message from the joined Sandbox account.
6. Confirm the inbound webhook returns HTTP 200 with no customer-facing TwiML.
7. Confirm exactly one proactive WhatsApp reply is received.
8. Inspect redacted database metadata: one delivery, one attempt, a non-null
   provider Message ID, and state at least `accepted`.
9. Observe a later status callback when available and confirm monotonic state.
10. Retry the same inbound callback and confirm no second REST submission or
    customer-visible reply.

## Execution record

- Date/time and timezone: 2026-09-23, America/Sao_Paulo
- Candidate baseline: `8aa2615995132b4bdf1c842a366ff103cace2c3c`
- Result: not executed
- Expected: one acknowledgement-only inbound response, one REST-created Message,
  one persisted MessageSid, state `accepted` followed by optional monotonic
  status, and no TwiML duplicate.
- Observed: the local environment had no `.env`, Twilio Auth Token, Account SID,
  API key, public inbound URL, or public status callback URL. No external request
  was attempted and no success was claimed.
- Required human gate: provide the credentials through local environment
  variables, join the Sandbox, and expose both callback URLs through HTTPS.
