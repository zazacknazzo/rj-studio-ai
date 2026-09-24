# Meta WhatsApp Cloud API smoke test

Status: pending manual Meta Console setup and explicit send approval

This is the real E2E gate for Messaging Migration 06. Use only Meta's official
test phone number, a registered test recipient, synthetic content, and a fresh
ignored SQLite database. Do not connect the RJ Studio production number.

Official contract references:

- [Meta WhatsApp Business Platform official workspace](https://www.postman.com/meta/whatsapp-business-platform/documentation/wl)
- [Send text message](https://www.postman.com/meta/whatsapp-business-platform/request/8gvd47s/send-text-message)
- [Received text payload](https://www.postman.com/meta/whatsapp-business-platform/request/cy6hnq7/received-text-message)
- [Webhook payload reference](https://www.postman.com/meta/whatsapp-business-platform/folder/tduohwq/webhook-payload-reference)

## LOCAL / AUTOMATIC

1. Create a fresh ignored database and configure:
   `WHATSAPP_PROVIDER=meta`, `DELIVERY_MODE=proactive`, one application process,
   the Graph API version selected in Meta, and all five `META_WHATSAPP_*`
   variables from `.env.example`.
2. Start the application and a TLS-valid public tunnel to port 8000.
3. Confirm local `/health` and `/ready` return HTTP 200 and the public `/health`
   returns HTTP 200 with normal TLS verification.
4. Use `https://PUBLIC_HOST/webhooks/meta` as the callback URL. The same path
   handles GET verification, authenticated inbound messages, and status events.
5. After Meta Console setup is complete, confirm a signed webhook fixture is
   accepted locally and an invalid signature is rejected. This is diagnostic;
   it does not replace the real Meta callback.

## MANUAL META CONSOLE

1. Open [Meta for Developers — Apps](https://developers.facebook.com/apps/),
   select the test app, then open **WhatsApp → Configuration**.
2. Under Webhook, choose **Edit**, enter
   `https://PUBLIC_HOST/webhooks/meta` as Callback URL and the exact local
   `META_WHATSAPP_VERIFY_TOKEN` as Verify token. The verify token is secret-like
   operational configuration; do not post it in chat or commit it.
3. Subscribe the WhatsApp Business Account to the `messages` webhook field.
   Inbound messages and sent/delivered/read/failed statuses arrive through this
   field; no additional field is required for M06.
4. Open **WhatsApp → API Setup**. Copy the test **Phone number ID** into
   `META_WHATSAPP_PHONE_NUMBER_ID` and a current access token into
   `META_WHATSAPP_ACCESS_TOKEN`. Copy the app secret from **App settings →
   Basic** into `META_WHATSAPP_APP_SECRET`. Tokens and the app secret are
   secrets and must never be sent in chat.
5. Add only a controlled personal number as a test recipient. Use the Meta test
   number shown on API Setup; do not register, migrate, or connect the RJ Studio
   production number.
6. Restart the application after changing `.env`, then reconfirm `/ready`.

Temporary dashboard tokens are acceptable only for this development smoke.
Production must use a supported long-lived/system-user credential with the
permissions shown by Meta for the selected WABA; credential lifecycle setup is
outside M06.

## REAL SMOKE — REQUIRES EXPLICIT APPROVAL BEFORE SENDING

1. Send one synthetic inbound text from the registered test recipient to the
   Meta test number.
2. Verify durable inbound persistence before HTTP ACK, asynchronous processing,
   one AI Reply, one Outbound Delivery, and one Provider Acceptance with a
   redacted `wamid`.
3. Verify exactly one reply is visible in WhatsApp and observe sent, delivered,
   or read status when available.
4. Replay the same authenticated inbound fixture and verify no extra generation,
   delivery, or visible reply.
5. Record date/time, commit, expected and observed behavior, redacted state
   evidence, and the status callback evidence. Do not record phone numbers,
   message bodies, tokens, app secret, full WABA/phone IDs, or full `wamid`.

The smoke fails closed if the free-form reply is outside the 24-hour customer
service window. M06 does not select or submit templates automatically. An
ambiguous outbound result remains `unknown` and must not be retried.

## Execution record

- Result: not executed
- Gate: manual Meta Console setup, then explicit approval to send the controlled
  WhatsApp message.
