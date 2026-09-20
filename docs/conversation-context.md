# Conversation Context

`ConversationContextBuilder` prepares one LLM request from canonical persisted
Messages and selected approved Salon Knowledge. It never receives provider IDs,
addresses, claims, lease data, timestamps, or generation metrics.

The default limits are configured through `.env`:

```dotenv
CONVERSATION_CONTEXT_MAXIMUM_MESSAGES=12
CONVERSATION_CONTEXT_MAXIMUM_AGE_DAYS=30
CONVERSATION_CONTEXT_HISTORY_TOKEN_BUDGET=2000
LLM_INPUT_TOKEN_BUDGET=4000
```

The current Customer Message is represented once and is never truncated. Its
relevant approved Salon Knowledge is selected before history. History is then
loaded only from the same Conversation, ordered as Customer then AI Attendant,
and trimmed from the oldest turn first. A reply associated with an earlier
inbound Message retains that logical position even when its database row was
inserted after a later inbound webhook arrived.

If history was excluded by the age window, Message cap, or byte budget, the
context carries a deterministic incomplete-history flag. The provider prompt
then tells the model to request clarification instead of inferring an omitted
antecedent. Retained Service facts never lose their required policy facts when
knowledge is trimmed for the total budget.

The token approximation is conservative UTF-8 byte length for the compact
context text, plus a fixed 400-byte reserve for stable provider instructions
and envelopes. It does not call an external tokenizer. A current Message that
cannot fit is not truncated or sent to the LLM; the existing safe-reply path
completes it without generation. Malformed stored timestamps fail safely.

This is recent Conversation continuity only. It creates no summary, Customer
profile, preference, Lead state, or cross-Conversation memory.
