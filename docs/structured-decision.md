# Structured decision

`LLMDecision` is the provider-neutral result of one LLM generation. It is a
validated proposal, never an authority over approved Salon Knowledge, factual
claims, or Human Handoff policy.

The contract carries one or more approved `Intent` values, short `reply_text`,
categorical `uncertainty` (`low`, `medium`, or `high`), selected
`knowledge_refs`, structured `critical_claims`, and a proposed `handoff` plus
reason. The reply has an 800-character hard structural limit and the Anthropic
request has a 200-token output limit.

The Anthropic adapter uses the official JSON-schema output mechanism, parses its
response, and validates it against the current selected approved knowledge. A
missing field, unknown enum, duplicate Intent/reference, unknown field, invalid
reference, invalid handoff combination, or malformed payload becomes the safe
`invalid_structured_decision` generation failure. No raw provider dictionary
crosses into application code and no full payload is logged.

Ticket 09 will validate factual values and deterministic Human Handoff rules. A
valid reference, a `handoff=false` proposal, and valid JSON do not make a reply
factual or safe by themselves.
