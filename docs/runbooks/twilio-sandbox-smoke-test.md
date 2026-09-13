# Twilio Sandbox smoke test

Status: pending

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

- Date/time and timezone: pending
- Tested commit: pending
- Result: pending
- Synthetic Message sent: pending
- Expected: one HTTP 200 callback, one configured Automatic Reply, one inbound
  row, and one outbound row
- Observed: pending
- Redacted evidence: pending
- Steps executed: pending
