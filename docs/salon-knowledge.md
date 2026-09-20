# Salon Knowledge

The versioned source is [knowledge/rj_studio.yaml](../knowledge/rj_studio.yaml).
It currently has no real approved facts. Add only institutional information that
the RJ Studio operator has reviewed; never add Customer data, credentials, or
assumptions.

Each `facts` item needs a stable lowercase `id`, `category`, Portuguese `topic`,
`status`, `fact_type`, `statement`, `source`, and `reviewed_at`. An approved
fact also needs `approved_by`.

`fact_type: operational_commercial` covers identity, location, channels, hours,
Services, prices, Professionals, policies, and handoff conditions.
`fact_type: technical` needs `validated_by: [Joelma]`, `[Rogério]`, or both
before it can be approved. Technical drafts may be stored but are never
selectable.

Only `status: approved` enters the runtime set. `draft` and `pending` are
validated as files but excluded from selection. A malformed file, duplicate ID,
or invalid policy reference rejects the entire load; no partial fact set stays
available.

For a Service, use `requires_human_consultation: true` and
`mandatory_policy_ids` when applicable. The referenced policy must exist and be
approved before that Service is approved. Selection uses stable matching against
the explicit `topic`, so a generic word in a fact's statement cannot select a
different Service's fact. Its budget is the UTF-8 byte upper bound of a compact
model-context representation (`id`, category, topic, type, statement, and
applicable Service rules). This deliberately conservative bound includes
Service-linked mandatory policies as one unit or omits that unit when it does
not fit.

Review the YAML change in Git, then validate it by starting the application or
running the focused tests:

```bash
.venv/bin/pytest tests/test_salon_knowledge.py
.venv/bin/uvicorn rj_studio_ai.main:app --port 8000
```

Startup validates the configured `SALON_KNOWLEDGE_PATH`. The Anthropic adapter
does not load YAML directly. Ticket 05 only establishes trusted source and
selection; it does not yet make factual claims or enforce grounding in AI
Replies.
