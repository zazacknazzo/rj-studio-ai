# V1 Coexistence — Ticket 01: neutral contracts and classification

Status: approved

Approval is limited to Ticket 01, with the owner's explicit amendment separating
edits and revocations. Tickets 02–13, live onboarding and messaging remain outside
this approval. Baseline: `7495fb8e47482a2cba2958ef4bf4e6a210b6c018`.

## Scope and acceptance

Define immutable provider-neutral values for six distinct categories: legitimate
Customer input, outbound human activity, delivery status, channel lifecycle,
message edit and message revocation. Canonical classification must reject unknown
objects rather than infer Customer input from a text field. Only Customer input
belongs to `InboundMessage`; none of the operational events carries AI Reply text.

Preserve existing Meta/Twilio constructors, positional fields, canonical meanings,
sender interfaces and legacy input. Prove compatibility with their existing tests.
No persistence implementation, migration, pause/resume, operator authentication,
Telnyx parser/webhook, sender or production factory changes belong to this ticket.
No prompts, persona, policies or Agentic Surface changes are authorized.

## Contracts

| Value | Meaning |
| --- | --- |
| `InboundMessageReceived` | Original Customer text; remains an `InboundMessage` |
| `HumanMessageObserved` | Human outbound activity; never Customer input |
| `DeliveryStatusReceived` | Sent/delivered/read/failed evidence, separate from acceptance |
| `ChannelAvailabilityChanged` | Account/channel lifecycle requiring blocking or verification |
| `MessageEdited` | Change observation with a separate original Message reference |
| `MessageRevoked` | Revocation observation with a separate original Message reference |

`classify_provider_event` classifies exact canonical types. It does not parse wire
payloads, inspect body text for event names, verify authenticity, or dispatch work.
Unknown types (including unknown subclasses), raw dictionaries and acceptance
objects fail closed. `InboundMessage` itself retains its historical internal input
meaning; it is not an additional provider webhook event.

`ProviderEventMetadata` is per event, rather than per batch, because one callback
can contain several messages/statuses with different identities and provenance.
It contains an event ID, explicit origin, timezone-aware occurrence time, optional
Message aliases and optional Message occurrence time. Metadata is keyword-only
and optional on existing inbound/status values; missing metadata means unavailable
provenance, not a fabricated event ID or timestamp. Existing adapters remain
unchanged. Metadata is mandatory on the four new operational values.
The current store does not persist the new metadata or submission key; enabling
an adapter that depends on their durability must wait for the appropriate tickets.

Inbound metadata, when supplied, requires Customer origin; human observations
require human-operator origin; status/lifecycle require provider origin. Edits and
revocations explicitly identify Customer or human-operator origin and never become
new ordinary text. Direction is implied by these distinct types. Adapters must
check wire direction and origin before constructing them; the types cannot detect
an adapter deliberately mislabeling a payload.

New Message observations contain provider, provider Message ID, channel ID and
Customer address. These are opaque identities, without phone-format assumptions.
Status has optional keyword-only channel/Customer correlation fields. Lifecycle
instead has explicit account/channel scope and resource ID; it has no Message ID
or Customer. Reconnection is a lifecycle observation, not sending authorization.

## Identity and ordering invariants

- `metadata.event_id` identifies the event envelope; `provider_message_id`
  identifies its logical Message subject. They occupy different semantic spaces,
  even when an external service happens to use the same string.
- Retransmissions may share an event ID; two distinct envelopes can refer to one
  Message. No event deduplication is implemented here.
- `MessageReference(namespace, message_id)` preserves alternate upstream IDs and
  original edit/revoke targets without guessing a namespace from string shape.
  The original target is separate from the change's own Message ID and aliases.
- Future dedupe/correlation must include provider and verified account/channel
  scope. Do not merge across providers or Customers solely on alias equality.
- Event occurrence and Message occurrence are separate from local receipt time
  and signature timestamp. Their presence does not prove authenticity or order.
- Manual observations, edits and revocations carry no replacement text and cannot
  be persisted as an AI Reply through the existing supported-event ingress.

## Acceptance, concurrency and future submission key

`ProviderAcceptance(provider_message_id)` keeps its exact existing shape. It only
confirms provider acceptance of submission; it neither adds a delivered status nor
enters `ProviderWebhookEvent`. Delivery confirmation still requires independent
status evidence. The existing conservative handling of `unknown` is unchanged.

No operator or concurrency token is introduced. Existing episode/owner tokens
coordinate ownership and compare-and-set; they are not credentials. Event origin
is adapter-supplied provenance, not authenticated operator identity.

`OutboundMessage.submission_key` is an optional keyword-only neutral string. This
ticket only makes it representable; no generation, storage or HTTP mapping occurs.
Current Meta/Twilio senders ignore it and existing callers retain `None`.

A later ticket can derive a stable key from the durable local delivery ID plus a
persisted installation namespace and provider/channel identity, e.g. a versioned
UUIDv5 derivation. A bare SQLite integer is insufficient: IDs can recur in another
database or after an unsafe restore. The resulting key must be persisted before
first submission, associated with immutable recipient/content, and reused across
restart and proven-safe retries. A random UUID persisted once per delivery is
another valid implementation. Do not derive the key from webhook event ID,
attempt number, concurrency owner token, text, or provider Message ID (which may
not exist until acceptance). A later sender may map it to an Idempotency-Key
header; this ticket makes no claim about provider retention or exactly-once sends.
Neither strategy permits automatic resend of `unknown`.

## Verification and residual limits

`tests/test_coexistence_contracts.py` covers all six categories, invalid and
contradictory provenance, separate event/Message/target/alias identities, immutable
metadata, acceptance separation and legacy constructors. It also uses a fake
adapter through the actual runtime to prove operational values never generate an
AI Reply in legacy or proactive mode. Existing Meta/Twilio tests retain their
wire parsing and outbound contract expectations.

The current store deliberately rejects the new operational types before opening
its write transaction, including mixed batches. Proactive ingress currently
propagates this unsupported-event error (HTTP 500 without a test exception
transport); legacy ingress returns 400. This is not production Telnyx support.
No route or factory selects a Telnyx adapter, and no event is silently acknowledged
as processed. A future enabled ingress must implement explicit durable handling
before emitting these values to the store.

Ticket 02 must define scoped unique keys, alias collision policy, atomic receipt
and effect, journal/tombstone retention, lifecycle revision and migration safety.
It must preserve optional legacy provenance without backfilling invented evidence.
Pause/fencing, authentication, parsing, status reconciliation and sending remain
the subsequent tickets' responsibility. Echo completeness and real-provider
payload validation are not established by contract tests.

## Recorded validation — 2026-10-31

- Full offline suite: **1172 passed, 1 skipped**, including **54 new contract cases**.
- Skip: `test_historical_v8_record_remains_loadable` requires local historical
  evidence not checked into Git; no provider/contract test was skipped.
- `ruff check .`, `ruff format --check .`, `compileall` for src/tests and
  `git diff --check` passed.
- Validation used a clean process environment, no commercial `.env`, synthetic
  data and an inherited Python audit guard blocking IP socket connections/sends.
- An initial test run found nine fixture invocation failures (missing keyword
  `outcomes=` on the existing fake sender); corrected before the passing full run.
- No production adapter, configuration, persistence, executor or intelligence
  source file changed. Only canonical contracts and acceptance documentation in
  `providers/base.py` changed in production code.
