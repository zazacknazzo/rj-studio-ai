# Render customer-visible facts exclusively from trusted sources

Status: accepted

A valid model reference or structured claim does not prove the correctness of
its free-text answer. Ticket 09 uses a small provider-neutral reply plan:
approved fact IDs render their complete immutable statements, and phrase IDs
select institutional conversational text. Model prose is never sent; approved
policies override model proposals before the existing atomic reply/outbox
completion. No messaging lifecycle or persistence schema changes are required.

We deliberately restrict free stylistic generation to phrase selection and
fact ordering. A numeric filter misses invented nonnumeric facts and semantic
alterations; another LLM cannot provide a deterministic guarantee. Rendering
complete statements preserves prices, conditions, and negation without building
a generic template or agent framework. Naturalness and the larger structured
output must still pass the V1 eval gate before a pilot. Approved source quality
and selection relevance remain operational responsibilities.

Empty/invalid plans and unsupported facts fail safely. The model retains
multi-Intent, uncertainty, references, and a handoff proposal, but cannot cancel
trusted human-review rules. Ticket 10 remains responsible for durable Human
Handoff; this renderer does not announce a transfer or claim suspension exists.
Deterministic configured replies remain a separate explicitly trusted path.
