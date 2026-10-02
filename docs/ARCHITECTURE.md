# Architecture

This document distinguishes the implemented baseline from the approved target.
The runtime baseline is V1 through Ticket 11 plus Messaging Migrations 01–06.
ADR 0006 owns the messaging migration. Twilio remains available and Meta
WhatsApp Cloud API is the next E2E target.

## Implemented runtime

Ticket 12's `evaluation` package is isolated from the production provider factory.
Its OpenAI-only live collector uses synthetic SQLite, existing policy seams and
a fake outbound sender. See [partial eval execution](evals/V1/openai-partial-2026-10-02.md)
for billing/evidence boundaries; it does not configure production or live messaging.

Delivery mode is an explicit process-level setting. `legacy` remains the safe
default and preserves the synchronous TwiML path for controlled rollback.
`proactive` separates ingress, AI processing, and customer delivery:

```text
Selected provider webhook
  → provider authentication and canonical inbound/status batch
  → persist inbound and message_processing work in one short transaction
  → return acknowledgement-only TwiML after commit

SQLite → lifespan Processing Executor → ordered generation claim
  → start one 10-second processing budget
  → bounded Conversation Context + approved Salon Knowledge
  → deterministic or Anthropic generation outside SQLite transaction
  → validated LLMDecision and privacy-safe metrics
  → trusted reply parts rendered from selected approved facts and institutional phrases
  → one transaction persists AIReply, pending OutboundDelivery, completed processing,
    and any required Conversation handoff

SQLite → lifespan Outbound Executor → provider-filtered delivery claim
  → Twilio or Meta REST API → provider Message ID → Provider Acceptance persisted

Provider status callback → authentication → monotonic sent/delivered/read/failed
```

The proactive webhook never waits for a predecessor or runs the LLM. Durable
polling finds retryable and expired processing claims after restart. A later
Message waits in SQLite until its predecessor reaches Provider Acceptance or
another explicitly approved terminal outcome. Manual recovery remains an
operator fallback and uses the current delivery mode.
Because polling begins after the durable commit, processing may start before
the provider receives the HTTP acknowledgement. The webhook does not call or
wait for the LLM; no delivery relies on the acknowledgement being observed.
Shutdown closes the short generation-claim gate before stopping polling, so it
cannot acquire new work once shutdown begins. Readiness rejects a switch back
to `legacy` while any nonterminal generation or unresolved proactive delivery
remains at startup; those rows must be drained or recovered before rollback.
This startup gate avoids changing readiness during an ordinary legacy webhook
that temporarily owns a generation claim.

Ticket 09 finalizes untrusted LLM proposals in `grounding.py`. Free model prose
cannot reach the AI Reply; approved statements are inserted unchanged and
mandatory policies are enforced independently of model references. Persona
limits and identity transparency apply to the rendered result. Deterministic
fixed replies remain explicitly trusted for V0 compatibility. See
[structured decision](structured-decision.md) and ADR 0007 for this contract.
Ticket 10 persists Human Handoff activation, suppression, and explicit release.

The SQLite model contains one Outbound Delivery per AI Reply and minimal
Delivery Attempt evidence. Proactive generation completion atomically creates
a `pending` delivery. The legacy TwiML path instead records
`accepted_legacy` only after successful rendering; failed rendering remains
`unknown` for a safe retry. Historical replies without evidence are also
`unknown` and never become eligible for automatic send.

## Implemented provider contracts

Messaging Migration 01 separates the seams while keeping the synchronous path:

- `InboundWebhookAdapter.receive()` authenticates and returns an immutable
  canonical batch of `InboundMessageReceived` and/or `DeliveryStatusReceived`
  events; Meta can return supported inbound and status siblings in one batch;
- `InboundWebhookAdapter.acknowledge()` renders provider acknowledgement with no
  customer-facing AI Reply;
- `LegacyWebhookReplyRenderer.render_legacy_reply()` explicitly owns the
  transitional non-empty TwiML response;
- `OutboundMessageSender.send()` accepts a canonical `OutboundMessage`, a
  timeout, and returns `ProviderAcceptance` with a canonical provider Message
  ID or one of the approved provider-neutral failures;
- `DeterministicFakeOutboundSender` records calls and consumes explicit
  accepted, retryable, permanent, or unknown outcomes.

`TwilioOutboundSender` maps canonical outbound content to the Twilio Message
resource. A lifespan Outbound Executor polls SQLite with configurable bounded
concurrency and an optional in-memory wake-up. The Processing Executor follows
the same polling principle with a separate claim and deadline. Status callbacks use the same
Twilio signature validation boundary and retain unmatched canonical status
evidence until MessageSid correlation becomes available.

`MetaProvider` verifies the subscription challenge and authenticates POST bodies
with the app secret before parsing. One authenticated batch is persisted in one
SQLite transaction before ACK; unsupported event types are ignored without
discarding supported siblings. `MetaOutboundMessageSender` submits eligible
text through the configured Graph API version and preserves the returned
`wamid`. Free-form eligibility requires a durable inbound from the same Meta
Customer/channel within 24 hours. The provider-selected delivery claim prevents
pending work from another adapter from being submitted through the wrong sender.

Delivery claims use a durable owner token, 30-second lease, attempt count, and
stale-owner checks. A stale `sending` claim becomes `unknown`; it is never
returned to `pending` or retried automatically. Accepted, unknown, and terminal
outcomes survive restart. SQLite transactions end before the sender is called.

## Approved target

```text
Provider webhook
  → provider-specific authentication and parsing
  → canonical inbound or delivery-status event
  → persist event
  → commit
  → provider acknowledgement

SQLite
  → Processing Executor
  → claim oldest eligible inbound in a Conversation
  → bounded context + knowledge + LLM + deterministic policy
  → one transaction:
       INSERT AIReply
       INSERT OutboundDelivery(pending)
       UPDATE message_processing(completed)

SQLite
  → Outbound Executor
  → claim oldest eligible delivery in a Conversation
  → revalidate owner, delivery eligibility, and handoff policy
  → provider REST submission
  → persist Provider Acceptance or failure outcome

Provider status webhook
  → persist monotonic sent/delivered/read/failed evidence
```

Ingress, processing, and delivery are separate modules with separate deadlines.
SQLite is the durable source of work. In-process wake-ups may reduce latency but
are never required for recovery. Executors poll durable state and keep every
SQLite transaction short. Expired processing leases are reclaimable; an expired
outbound `sending` lease becomes `unknown` because submission may have occurred.
No transaction spans LLM work, sleep, backoff, or an external request.

## Messaging concepts and guarantees

- An inbound Message received is distinct from an AI Reply generated.
- An AI Reply generated is distinct from an Outbound Delivery accepted.
- `(provider, provider_message_id)` uniquely identifies an inbound.
- The existing reply link permits at most one logical AI Reply per inbound.
- A unique Outbound Delivery link permits at most one delivery intent per AI Reply.
- Generation completion atomically persists the AI Reply, pending delivery, and completed processing state.
- Local logical reply preparation has strong uniqueness across retries and restart.
- External provider submission is not exactly once. Definitively retryable failures use bounded at-least-once submission.
- A submission whose outcome is ambiguous becomes `unknown`; it is never retried automatically and blocks that Conversation pending explicit reconciliation, recovery, or Human Handoff.

A failure is definitively retryable only when the provider contract proves that
the request was not accepted. Timeout, connection loss, malformed response, or
undocumented provider failure semantics are `unknown`, not generic retries.

Provider Acceptance means that the provider accepted the submission and
returned a provider Message identifier. It does not mean `sent`, `delivered`,
or `read`. Later automated processing may cross this boundary without waiting
for delivery/read callbacks. If an accepted delivery later becomes `failed`,
history already used is not rewritten; future automation in that Conversation
is blocked for policy or recovery.

## Conversation ordering and context visibility

Generation claims remain ordered by persisted inbound ID. Different
Conversations may run concurrently. Within one Conversation, later automated
processing waits until the predecessor is terminal and any predecessor AI Reply
has reached Provider Acceptance, explicit `accepted_legacy`, or operator-selected
`cancelled` state. Cancellation releases ordering without treating the unsent
reply as Customer-visible. Processing does not wait for `delivered` or `read`.

Conversation Context includes an AI Reply as assistant speech only when its
Outbound Delivery is `accepted`, `sent`, `delivered`, `read`, or explicitly
`accepted_legacy`. Replies with `pending`, `sending`, `retryable`, `unknown`,
`failed`, or `cancelled` delivery are not treated as customer-visible. An
accepted delivery that later reports failure blocks future automation instead
of retroactively changing context already used.

## Provider seams

The original `WhatsAppProvider` interface remains the implemented V0.1 seam.
The target separates two responsibilities:

- inbound adapter: authenticate, parse provider webhooks into canonical events, and create the provider acknowledgement;
- outbound sender: submit one canonical outbound Message and return accepted, retryable, permanent, or unknown outcome.

Twilio will acknowledge inbound callbacks without embedding the AI Reply and
will submit outbound Messages through its REST API. Meta will parse inbound and
status events, use `phone_number_id` as the durable channel identifier, submit
through `/messages`, and persist the returned `wamid`. Provider SDK values do
not cross the seam.

## Delivery lifecycle

The target lifecycle distinguishes:

```text
pending → sending → accepted → sent → delivered → read
              ├─→ retryable → sending
              ├─→ unknown
              └─→ failed
pending/retryable → cancelled
```

`accepted_legacy` explicitly marks a reply with sufficient legacy-path delivery
evidence. The current schema cannot prove that for every historical row,
especially a reply created by manual recovery. Unverified rows migrate to
`unknown` with a legacy-unverified reason and block automation until explicit
reconciliation; no historical reply becomes `pending`. Duplicate status
callbacks are no-ops. Statuses arriving before local acceptance finalization
are durably retained for later correlation. Out-of-order success callbacks can
only advance evidence; they cannot downgrade delivered/read.

Before every external submission, the outbound executor revalidates the owner,
delivery eligibility, and current Human Handoff policy. A handoff can
cancel work not yet submitted. A request already in flight cannot be recalled;
handoff guarantees must state that residual race explicitly.

## Durable Human Handoff

`conversation_handoffs` holds one current episode per Conversation: active flag,
safe reason, episode owner token, activation time, and explicit release time.
Owned generation completion atomically creates the confirmation and outbox,
completes processing, activates the episode, cancels proven-unsubmitted work,
and suppresses waiting Messages. New inbound inserts during handoff receive the
terminal processing state `suppressed`. Release never revives them.

Only the current episode's confirmation may submit during active handoff.
Delivery authorization commits `submission_started_at` just before external
HTTP; cancellation can include a claimed delivery only before this marker.
Possible in-flight work retains provider outcomes, including `unknown`.
Manual release uses an episode-token compare-and-set and cancels an unsent
confirmation; it does not reconcile unknown/failed deliveries or promise that
automation can cross an unresolved ordering barrier. Purge preserves active
handoff state even after its Messages expire.

[ADR 0008](decisions/0008-durable-human-handoff.md) owns the migration and race
trade-offs. [Human Handoff operations](human-handoff.md) owns local list/release
commands. Ticket 11 adds one bounded appointment-interest episode per
Conversation; its preferences, clarification counter and handoff link commit
with owned generation completion. The LLM proposes current-Message excerpts,
never availability or salon facts. See [appointment interest](appointment-interest.md)
for episode, two-question, release, retention and explicit inspection rules.

## Deadlines and recovery

- Ingress deadline covers authentication, parsing, one short persistence transaction, and acknowledgement.
- Processing retains the approved 10-second attempt-sequence budget initially, starting when an executor acquires the Message. All attempts share that budget. The 30-second generation lease remains separate.
- Outbound submission has its own request deadline shorter than its delivery lease.
- Product latency is measured from inbound persistence to Provider Acceptance; it is not one synchronous HTTP timeout.

Automatic durable polling becomes the normal recovery mechanism for retryable
and stale processing claims plus pending/definitively-retryable deliveries.
Stale `sending`, unknown, and terminal outbound work requires explicit operator
reconciliation. The maintenance command remains that fallback. A Message must
reach a terminal or explicitly blocked state after its attempt policy; it
cannot stay as an immortal predecessor.

## SQLite deployment gate

Early webhook acknowledgement is forbidden until all of these are true:

- `journal_mode=WAL` is applied and verified;
- `synchronous=FULL` is applied while durability-before-ACK is required;
- `foreign_keys=ON` is applied to every runtime and migration connection;
- a uniform `busy_timeout` is applied;
- claim, due-work, and Conversation-order indexes exist;
- the database uses persistent local storage;
- exactly one application process owns the database;
- readiness rejects observable pragma, schema, executor-health, or configuration mismatch.

Persistent storage and single-process deployment are operational invariants;
readiness cannot infer an infrastructure guarantee that deployment did not
declare. SQLite remains appropriate for the pilot. Postgres, Redis, queues,
distributed workers, and horizontal scaling remain out of scope.

## Current modules retained through migration

| Existing module | Target role |
| --- | --- |
| `main.py` | Composition root, ingress routes, lifespan-managed executors, health/readiness |
| `application.py` | Processing coordination outside the webhook request |
| `deadline.py` | Separate monotonic budgets for ingress and processing; outbound uses its own request timeout |
| `processing.py` | Deterministic one-step runner and lifespan Processing Executor |
| `conversation_context.py` | Bounded context filtered by delivery visibility |
| `generation.py` and `providers/anthropic.py` | LLM seam and Anthropic adapter, unchanged in purpose |
| `grounding.py` | Trusted reply composition and deterministic human-review overrides before completion |
| `handoff.py` | Localized safe reasons and truthful one-time confirmation, including technical-risk guidance |
| `persistence.py` | Durable inbound, processing claims, outbox/claims, monotonic status merge, early-status inbox, ordering, and redacted inspection |
| `delivery.py` | Deterministic runner plus lifespan-managed durable outbound polling |
| `providers/twilio.py` | Twilio inbound adapter and REST outbound sender |
| `providers/meta.py` | Meta verification/signature boundary, webhook adapter, and REST outbound sender |
| `providers/base.py` | Implemented inbound, acknowledgement, legacy renderer, and dormant outbound sender contracts |
| `providers/fake.py` | Deterministic outbound contract fake; never selected by production configuration |
| `recovery.py` | Manual fallback after automatic executor recovery is introduced |

The migration adds only seams justified by Twilio/Meta variation and critical
crash testing. It does not add a generic repository, job framework, event bus,
or multi-tenant infrastructure.

## Rollout sequence

1. **Implemented:** separate provider inbound acknowledgement and outbound sender contracts with a deterministic fake; retain current external behavior.
2. **Implemented:** enforce SQLite durability prerequisites and readiness gates.
3. **Implemented:** add legacy-safe Outbound Delivery schema, transactional outbox, and provider-neutral deterministic runner seam.
4. **Implemented:** add proactive Twilio REST delivery, delivery claims, status callbacks, and safe legacy/proactive cutover.
5. **Implemented:** move processing to durable polling, acknowledge after ingress commit, remove predecessor HTTP 503, and separate deadlines. Real Twilio smoke remains an operational gate.
6. **Implemented; real smoke pending:** add the Meta Cloud API adapter, atomic batch ingress, provider-filtered delivery acquisition, and 24-hour free-form channel-policy seam.

ADR 0006 owns this target. ADRs 0001, 0003, and 0005 retain their original
historical decisions and are explicitly amended where synchronous assumptions
were replaced.

## Deliberately deferred

- Multi-tenant routing or `tenant_id` before V7.
- Redis, broker, distributed workers, Postgres, horizontal scaling, or HA.
- Generic agent or integration frameworks.
- CRM, scheduling, multimodal, Google Ads, or campaign messaging.
- Automatic retry of unknown outbound outcomes.
- A promise of exactly-once external delivery.
