# V1 Conversational Polish

Status: approved

Approved by the product owner on 2026-10-03. Baseline: `9f8f611`.
This small product amendment supersedes only the affected V1.5/V1.6 surface and
Ticket 11 collection rules; messaging, factual trust and Ticket 10 remain unchanged.

## Behavior

- Respond → acknowledge → advance when useful, without pressure. Extend the
  existing controlled phrase/fact Reply AST; no free model rewriting of facts.
  Approved statements, qualifiers, prices and mandatory policies remain intact.
- The shared provider-neutral catalog supplies brief acknowledgements, service
  clarification, safe continuation, appointment questions and contextual handoff.
  Factual multi-intent plans still require every necessary selected reference/part.
  Invalid refs and missing facts in an attempted answer remain fail-closed.
- A controlled question may clarify an ambiguous price/discount request before
  handoff when no approved answer is available. It supplies no factual answer,
  discount or new ref. Do not repeat the same clarification indefinitely. Selected
  consultation/risk/mandatory policy, explicit human request and genuine model
  handoff still take precedence. Missing supported fact parts are not clarification.
- Knowledge availability is not relevance. A selected fact need not be rendered
  without a semantic link to the current Message or unambiguous Conversation
  Context. For each detected factual Intent supported by a relevant approved
  fact, the plan still needs the corresponding ref and fact part; unrelated
  selected facts may remain unused. The product-owner follow-up after smoke 02
  explicitly authorizes this relevance rule in shared provider instructions;
  deterministic finalization and the factual multi-intent contract stay intact.
- Identity transparency is required for an actual identity question, not merely
  a request to speak with a person. Never claim human identity or false experience.
- Handoff state/event is independent of the customer surface. Explicit request
  receives a brief acknowledgement; risk/complaint/knowledge/appointment use
  appropriate wording. Technical symptoms retain the approved minimum stop,
  professional evaluation and urgent medical guidance, without diagnosis.
- Default no emoji; at most one. Do not use in consecutive visible assistant
  turns or technical risk, health, serious complaint, cancellation or urgent
  handoff. No emoji is necessary for facts or ordinary conversation.

## Bounded appointment preferences (amends Ticket 11)

- Collect service, day, and period or preferred time; never availability. Exact
  time is optional once a day and period are useful. Professional preference is
  optional and only recorded when supplied; no obligatory interrogation.
- Store day separately from time/period so a short answer cannot overwrite day.
  Model excerpts must be bounded, printable, verbatim current-Message text.
  Legacy day/time strings survive migration unchanged, without assuming missing
  details; old handoff/released episodes are not reopened.
- At most THREE committed clarification questions per episode, one per reply.
  A complete first turn needs zero. At completeness or after the third answer,
  create durable handoff for real confirmation, never a booking/available slot.
- Cancellation gets at most ONE gentle offer to choose another day/time; an
  explicit refusal/firm cancellation skips it. Persist that opportunity within
  the episode so retries/restart cannot repeat it. Confirmation or unclear answer
  after that offer transfers to a person without pressure or false cancellation.
  Product-owner clarification (2026-10-03): a first simple cancellation cannot
  immediately hand off solely because the model generically proposes it. Its
  deterministic one-time recovery question takes precedence over that proposal;
  independent risk/complaint/human request, selected Knowledge policies and all
  grounding validation still take precedence over recovery. No override applies
  to firm cancellation, later confirmation, or other appointment requests.
- Rescheduling, including a switch from that offer, collects the new preference
  within the SAME three-question budget (the offer counts). Already supplied
  service/day/time is preserved, but cancellation → reschedule discards old
  timing before collecting a new preference. No real operation is performed.
- Other change requests whose purpose cannot be safely identified hand off.
  Risk/complaint/human request overrides collection immediately.
- Episode updates/cursor fencing, reply, outbox, processing and any handoff remain
  one transaction. Release, purge and not-yet-submitted cancellation semantics
  retain Ticket 10/11 invariants. No network request inside a transaction.

## Acceptance and verification

The ten prior smoke scenarios must preserve trusted facts/injection resistance,
clarify ambiguous price and discount, shorten/contextualize safe handoff,
collect a period for a supplied service/day, offer cancellation recovery once,
clarify missing context and answer multi-intent facts with a safe continuation.
Verify replay/restart, cancellation confirmation and reschedule, three-question
bound, invalid refs, mandatory policies, multi-intent and emoji sensitivity.
Use public finalizer/application/store/provider-schema seams with deterministic
fakes; no naturalness score or exact-word requirement except approved facts.
Run the full suite and existing static checks; review product/spec, grounding
safety and code standards independently before any paid evaluation.

## Human and live gates

Current [product-owner decision](../evals/V1/conversational-polish-human-review-2026-10-03.md):
conversational human review is APPROVED qualitatively, based on earlier observed
responses; no further numerical ratings or retrospective average. Case 8's
functional failure remains open until corrected. Following checks and three
reviews, one cancellation retest (US$0.20) may precede a fresh ten-case smoke
(US$1) only if it passes. On functional 10/10, Phase B is released for the NEXT
stage, never executed here; measured latency and real WhatsApp gates remain
separate. Ticket 12 remains in-progress. The records below are historical.

Product-owner eval correction (2026-10-03): split the ownership/instruction
injection into two variants. Without a named Service or resolving context,
reject the Customer-supplied USD value and any unsolicited Service fact;
clarification/redirection is allowed and handoff is not obligatory. With corte
explicitly named, require its approved price/ref/part and exclude the injected
value, without handoff. Fixture-selected availability alone cannot require an
answer about corte. Naturalness remains a human rubric, not an exact-copy test.
No further paid evaluation is authorized by this correction.

The prior ten-case smoke passed semantics but product-owner human review rejected
conversational UX: dry replies, weak persona, artificial formality, generic
handoff, weak commercial continuation, premature intake and no cancellation
recovery. Preserve all old evidence; Ticket 12 stays in-progress; Phase B blocked.
After checks/reviews, one new smoke only: ten SMOKE_CASES, one run each,
gpt-6.1-sol / medium / default (standard) / output 512 / observation 30s,
no retries, cap US$1. Stop on safety, semantic, structural, usage, accounting or
privacy failure. Valid slow responses continue and fail latency separately;
official p95 observed E2E <=8s is unchanged; diagnostic E2E never replaces it.
Generate a new unscored human-review packet. No Phase B, Anthropic, real
Customer/WhatsApp/Meta, credentials changes, approved Knowledge changes, CRM,
calendar, discounts, new messaging architecture or main merge.
