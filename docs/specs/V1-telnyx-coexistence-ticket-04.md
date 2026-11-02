# Coexistence Ticket 04 — outbound cancellation and authorization

Status: approved

Explicit authorization: Ticket 04 only, base 2417708e37bb633c6af3d0ec732b64baa61e629f.
Tickets 05–13, external APIs, onboarding, credentials and live sending are not authorized.

## Invariants

Operational pause and cancellation commit together. Cancel pending/retryable and
sending only when submission_started_at is NULL. Preserve attempts, counts, metrics,
Message bodies and every possible-submission marker. A started but unsubmitted
attempt finishes locally as failed with the controlled code
operational_pause_cancelled; this is a local cancellation, not a provider failure.
Completed attempts are never overwritten. Unknown (including legacy_unverified),
accepted, sent, delivered, read, failed and accepted_legacy are not cancelled by pause.
Existing handoff's legacy-unverified exception remains only outside operational pause.

Acquisition excludes paused Conversations. Authorization checks operational pause,
policy handoff, current owner, lease and absence of a prior submission marker in
one BEGIN IMMEDIATE transaction that writes the marker. Each claim authorizes only
once. The existing runner calls the sender after this transaction ends. Old work
cannot reclaim cancelled deliveries or renew authorization after pause. Legacy
reply authorization also respects pause without relabeling unknown as not sent.

If authorization wins the race, the in-flight result may be accepted, failed or
unknown after pause. Acceptance still merges early callbacks; monotonic status and
terminal failed precedence are unchanged. A proven retryable result after pause
retains its attempt evidence and atomically becomes cancelled, with no reschedule.
If the lease already expired, existing conservative unknown recovery applies.

Triggers implement cancellation at the control transition and on new pending/
retryable outbox states while paused. Migration 0016 installs guards and applies
safe cancellation to pauses already committed by Ticket 03, in the migration
transaction. No new tables or parent rebuild. Readiness requires the new triggers.
Unrelated Conversations and policy handoff without operational pause remain eligible.
Handoff confirmation is cancelled when still provably unsubmitted; release never
revives cancelled/suppressed work. Pause duplicates do not mutate cancellation evidence.

## State matrix

| Before pause | After pause |
| --- | --- |
| pending/retryable | cancelled; completed attempts preserved |
| sending, no marker | cancelled; started attempt finalized locally; owner invalidated |
| sending, marker present | preserved; may finalize accepted/failed/unknown |
| retryable response arriving during pause | attempt retryable retained; delivery cancelled |
| unknown, including unmarked legacy evidence | preserved; no automatic retry; legacy authorization blocked |
| accepted/sent/delivered/read/accepted_legacy | preserved |
| failed/cancelled | unchanged |

## Limits and validation

The durable marker is not atomic with external HTTP. A request authorized just
before pause may start after pause commits. No recall, external exactly-once or
compensating resend is promised. Echo is best-effort. Journal/control retention
without expiry remains a release blocker. Authenticated commands remain Ticket 05.
No API, adapter, sender, prompts/persona/grounding, CRM, SaaS or Idempotency-Key work.

Deterministic tests cover both race orders, pause before/after claim, rollback,
restart at claim/authorization/result boundaries, duplicates, pending/retryable,
marked/unmarked sending, unknown, late acceptance, early/out-of-order statuses,
handoff confirmation/release, two concurrent Conversations, privacy and legacy
Meta/Twilio. All send calls are in-memory fakes with IP network disabled. Run full
suite, Ruff, formatting, compilation, diff checks and independent Standards/Spec
reviews; fix material findings and add regressions before delivery.
