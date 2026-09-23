# Twilio Sandbox smoke test

Status: passed

This is the immutable V0.1 synchronous-TwiML acceptance record. It does not
accept ADR 0006. Messaging Migration 04 has a separate proactive-delivery smoke
record; Migration 05 will extend it with early acknowledgement and processing
restart recovery.

Use this runbook to accept V0.1 against the real Twilio WhatsApp Sandbox. Use a
fresh database and a synthetic Message. Never paste secrets, complete phone
numbers, tunnel credentials, or provider identifiers into this file.

## Prerequisites

- A WhatsApp account joined to the Twilio Sandbox.
- The Sandbox Auth Token in `.env`.
- An HTTPS tunnel forwarding to local port 8000.
- `TWILIO_VALIDATE_SIGNATURE=true`.
- `TWILIO_PUBLIC_WEBHOOK_URL` equal to the tunnel URL ending in
  `/webhooks/twilio`.
- A fresh ignored database path, such as `work/smoke/v0.1.db`.

## Steps

1. Install the project and set `DATABASE_PATH` to the fresh smoke database.
2. Run `rj-studio-maintenance migrate`.
3. Start `uvicorn rj_studio_ai.main:app --port 8000`.
4. Start the HTTPS tunnel and update `TWILIO_PUBLIC_WEBHOOK_URL`.
5. Set the Sandbox **When a message comes in** URL to that exact value with
   method `POST`, then restart the backend.
6. Confirm `GET /health` and `GET /ready` both return HTTP 200.
7. From the joined WhatsApp account, send the synthetic Message recorded below.
8. Confirm WhatsApp receives the configured Automatic Reply.
9. Confirm the webhook returned HTTP 200 in the tunnel or Twilio request log.
10. Query only counts and directions in the smoke database. Expect one inbound
    and one outbound row in one Conversation.
11. Stop the backend and tunnel. Delete the temporary database if its evidence
    is no longer needed.

Safe database verification:

```bash
sqlite3 work/smoke/v0.1.db \
  "SELECT direction, COUNT(*) FROM messages GROUP BY direction ORDER BY direction;"
```

## Execution record

- Date/time and timezone: 2026-09-13 10:50:55 -03:00
- Tested commit: `0e3071f`
- Result: passed
- Synthetic Message sent: `RJSTUDIO-V0.1-SMOKE-20260913-104938`
- Expected: one HTTP 200 callback, one configured Automatic Reply, one inbound
  row, and one outbound row
- Observed: Twilio called `POST /webhooks/twilio` with HTTP 200; WhatsApp
  received `RJ Studio V0.1 smoke OK`; SQLite contained one Conversation and
  exactly two Messages, one inbound and one outbound linked to that inbound.
- Redacted evidence: the server access log recorded
  `POST /webhooks/twilio HTTP/1.1 200 OK`; `/health` and `/ready` returned HTTP
  200 through the public tunnel; the database query returned
  `conversations=1`, `inbound=1`, `outbound=1`, and zero duplicate provider
  identifiers. No phone number, MessageSid, Auth Token, or tunnel credential
  was retained.
- Steps executed: activated and joined the Sandbox; migrated a fresh ignored
  database; started the backend with signature validation enabled; started an
  HTTPS tunnel; configured the exact `POST` webhook URL; checked liveness and
  readiness locally and through the tunnel; sent the synthetic Message;
  observed the reply; inspected redacted database counts and linkage; stopped
  the backend and tunnel; removed the temporary database and local secret file.
