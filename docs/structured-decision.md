# Structured decision

`LLMDecision` is the provider-neutral result of one LLM generation. It is a
validated proposal, never an authority over approved Salon Knowledge, factual
claims, or Human Handoff policy.

The contract carries one or more approved `Intent` values, proposed `reply_text`,
typed `reply_parts`, categorical `uncertainty` (`low`, `medium`, or `high`), selected
`knowledge_refs`, structured `critical_claims`, and a proposed `handoff` plus
reason. The reply has an 800-character hard structural limit and the Anthropic
request has a 200-token output limit.

Ticket 11 adds nullable `appointment_preferences` with `desired_service`,
`preferred_time` and optional `professional_preference`. Conversational Polish
adds `preferred_day`; new provider schemas require its nullable slot too. These are untrusted
Customer excerpts, not `critical_claims` or `knowledge_refs`. Older decisions
remain readable without this field; new provider requests require it (nullable).
See [appointment interest](appointment-interest.md) for trusted questions,
deterministic grounding precedence and durable handoff completion.

The Anthropic adapter uses the official JSON-schema output mechanism, parses its
response, and validates it against the current selected approved knowledge. A
missing field, unknown enum, duplicate Intent/reference, unknown field, invalid
reference, invalid handoff combination, or malformed payload becomes the safe
`invalid_structured_decision` generation failure. No raw provider dictionary
crosses into application code and no full payload is logged.

## Trusted rendering (Ticket 09)

Application finalization renders only these two part types:

```json
[
  {"kind": "phrase", "phrase": "formal_greeting"},
  {"kind": "fact", "knowledge_ref": "price-corte"}
]
```

Phrase IDs select a small institutional catalog in `livia_persona.py`; they
accept no custom text or values. Fact IDs must be declared in `knowledge_refs`
and refer to the current selected approved Salon Knowledge. `grounding.py`
inserts the complete approved `statement`, preserving numbers, currency,
duration, negation, and commercial conditions. Arbitrary model `reply_text`
never becomes customer-visible. Model `critical_claims` do not authorize facts:
the final claims are reconstructed from the rendered approved statements.

The model chooses phrase variants, fact ordering, and multiple Intents; it
cannot supply new factual prose. This restricts stylistic freedom deliberately
([ADR 0007](decisions/0007-trusted-reply-rendering.md)). No semantic reviewing
LLM or numeric regex is the grounding guarantee. New provider requests require
`reply_parts`; an older proposal without them is read safely but yields a
clarification. Future adapters return the same untrusted decision contract.

Selected availability does not establish factual relevance. A fact needs a
semantic link to the current Message or unambiguous Conversation Context before
being used. For each detected factual Intent supported by a relevant approved
fact, the plan still declares its ref and fact part, covering all such Intents;
unrelated selected facts may stay unused. This does not authorize omission of a
relevant price or policy. The eval-only selection/oracle distinction is defined
in [harness operations](evals/V1/harness.md). Following the live relevance
failure, the shared `reply_plan_instructions()` now makes that distinction
explicit for both providers: candidates do not imply an answer, Customer
assertions/override attempts are not factual requests, and a legitimate remaining
request still needs every relevant necessary ref/part. Undetermined Services
require clarification instead of an arbitrary candidate fact.

Relevance is currently a model-planning responsibility, not a deterministic
guarantee. Fact metadata has category/topic and approval rules, but no trusted
resolved request/entity or proof of the Customer's purpose. Finalization keeps
its category/ref/claim/mandatory-policy checks unchanged; it cannot prove a
semantic link just because the model chose a valid ref. A proposal declaring
`price` but omitting its part can still trigger `missing_critical_fact` when a
price candidate exists. This conservative handoff is preserved, not bypassed
by the new instruction. Controlled clarification tests demonstrate allowed
plans, not automatic Intent accuracy or relevance detection. Live evals must
still reject unsolicited facts; no lexical Service recognizer or secondary
verifying LLM was introduced.

Missing or invalid facts, unsupported claim categories, missing mandatory
policies, or an unsafe final surface produce a short deterministic clarification
or proposal for human review. Selected Services carry their mandatory policies
into the rendered reply even if the model omits them. A selected
`requires_human_consultation`, handoff condition, localized risk trigger, or
human-review Intent overrides `handoff=false`. Explicit AI identity questions
receive transparent identity text, including generation-failure paths. Persona
limits apply to the final rendering, never truncate a factual statement.

This policy returns a handoff **proposal**. Ticket 10's application finalization
normalizes its reason to a safe code and creates a trusted confirmation through
the atomic Conversation handoff completion. That transaction also persists the
AI Reply and Outbound Delivery, suspends automation, and suppresses waiting
Messages. Raw model reason text is not stored or echoed. Generation exhaustion
uses the same handoff path; recognized technical-risk and transparency rules
still apply. The whole LLM decision is not persisted.

See [Human Handoff operations](human-handoff.md) for explicit release and
[ADR 0008](decisions/0008-durable-human-handoff.md) for delivery race semantics.

`GeneratedReply.from_reply_text()` is reserved for trusted deterministic
configuration/test replies. LLM adapters must never call it with model data or
set `trusted_reply`; the Anthropic adapter leaves that field unset. Existing
fixed-response mode remains compatible. No historical reply is rewritten.

## Conversational Polish

The existing catalog adds acknowledgements, optional warm acknowledgement,
service clarification and safe continuation. Composition wraps intact fact
statements; it never calls an LLM after rendering or accepts custom phrase text.
A narrowly controlled price/discount service question may precede handoff when
no approved category answer is available, with no claims/refs, no repetition,
and no risk/mandatory-policy override. It cannot substitute for omitted
available facts or bypass invalid references. Appointment collection is allowed
only by the trusted intake planner passed by application, never a model flag.
Handoff confirmations depend on safe reason; durable activation is unchanged.
Identity disclosure answers identity questions, not simple human requests.
The approved [amendment](specs/V1-conversational-polish.md) owns product limits.
