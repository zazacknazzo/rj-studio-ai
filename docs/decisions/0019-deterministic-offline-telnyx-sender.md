# Bind exact Telnyx HTTP intent before an intercepted exchange

Status: accepted within explicit offline Ticket11 authorization, 2026-11-21.

Use fixed WhatsApp endpoint and deterministic UTF8 JSON, no SDK/default HTTP client.
An injected callable receives immutable prepared bytes with explicit no-retry/no-redirect
and connect/read budgets. The generic sender method fails closed; the runner prepares,
authorizes the exact request and dispatches that prepared object once.

Bind exact request including organization to T10 durable UUID using versioned keyed HMAC.
Persist no duplicate text/phone payload or new public predictable-content digest. A local
integrity key is injected independently of the restoreable DB, stable across restarts;
key change denies prior bindings. Migration0022 adds retained immutable request receipts
without rebuilding parent tables. Authorization checks lifecycle organization/profile and
all existing gates, then commits binding and markers in one short SQLite writer.

Accept only a strict identity-valid subset of the official200 response schema. Ledger T08
alone interprets delivery statuses. Every potentially submitted inconclusive result remains
unknown; HTTP429/5xx/timeouts and idempotency responses never grant automatic retry.
Preparation before invocation is local evidence; after a committed marker uncertainty wins.
No I/O in transactions, no body/auth/error details in logs, no runtime composition.

AUD01 is not solved by a MAC or another DB field. Restores require externally enforced
quarantine and independent reconciliation before operational composition. T11 adds offline
adversarial evidence and specifies this gate; T12–13 remain unauthorized. CX06 residual
authorization→HTTP race and unbounded retention CX01 remain explicit. Offline approval
cannot authorize real sending, account activation or production.
