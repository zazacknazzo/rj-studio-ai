# Twilio asynchronous ingress smoke test

Status: pending operational gate

This is the real Twilio Sandbox gate for Messaging Migration 05. Use synthetic
content, a fresh ignored SQLite database, one application process, and the
same credential hygiene as the M04 proactive smoke runbook.

## Steps

1. Complete the M04 proactive smoke prerequisites and configure
   `DELIVERY_MODE=proactive` with public inbound and status callback URLs.
2. Confirm `/ready` reports both `processing_executor` and
   `outbound_executor` as `ok`.
3. Send one synthetic inbound WhatsApp Message. Record the inbound webhook
   latency and confirm an empty customer-facing TwiML acknowledgement.
4. Confirm exactly one AI Reply arrives through Twilio REST. Verify one inbound,
   one completed processing row, one AI Reply, one delivery, and a persisted
   provider Message ID using redacted operational metadata.
5. Record inbound-persistence-to-Provider-Acceptance latency; observe a later
   status callback when available.
6. Repeat the inbound callback and verify it creates no extra generation or
   customer-visible reply.
7. With a fresh synthetic Message, stop the application after inbound ACK and
   before processing when operationally possible; restart and verify polling
   completes the same durable work once.

## Execution record

- Date/time and timezone: 2026-09-23 16:28 America/Sao_Paulo
- Candidate baseline: `cd958d88800f64f718a5621842e5b87bcd207e4c`
- Result: not executed
- Expected: durable inbound before ACK, asynchronous AI processing, one REST
  submission and Provider Acceptance, no customer-facing TwiML, restart
  recovery when the controlled timing permits.
- Observed: the local environment has no `.env`, Twilio credentials, or public
  HTTPS webhook/status URLs; Sandbox membership could not be verified. No real provider
  request was attempted and no success is claimed.
- Gate: configure the Sandbox privately, execute the steps, and record the
  tested commit and redacted evidence without secrets, phone numbers, raw
  MessageSid, or real Customer content.
