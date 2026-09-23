# Roadmap

## Delivery constraint

The planning clock starts on 2026-09-12, with V6 targeted no later than 2026-10-02. Protect that 20-day limit by keeping each version narrow, shipping complete vertical slices, and moving non-essential work to later versions. Acceptance criteria belong in the approved specification for each version.

| Version | Outcome | Scope | Status |
| --- | --- | --- | --- |
| V0 | WhatsApp infrastructure | Twilio-formatted webhook → backend → persistence → Automatic Reply | Complete |
| V0.1 | Pre-V1 foundation hardening | Durable retries, provider seam, migrations, readiness, retention, and failure-path tests | Complete |
| V1 | AI attendant | LLM, stable personality, Conversation context, Salon Knowledge, Intent detection, natural replies, hallucination protection | Approved; Tickets 01–08 and Messaging Migrations 01–04 complete; M05–M06 pending |
| V2 | CRM and memory | Customer profile, summarized history, interest, Lead Stage, objections, Lead Source, preferences, Next Best Action, initial lead scoring | Planned |
| V3 | Commercial engine | Policy-driven Next Best Action, consultative selling, objection handling, follow-ups, cross-sell, upsell, discount policy, Human Handoff | Planned |
| V4 | Scheduling | Real availability, Professionals and Services; create, reschedule, cancel; conflict prevention | Planned |
| V5 | Multimodal service | Audio, photos, initial hair analysis, technical questions, Human Handoff | Planned |
| V6 | Growth engine | Google Ads, GCLID/UTM, attribution across Lead → Appointment → Completed Service → revenue, enhanced/offline conversions, analytics, observability | Planned |
| V7 | SaaS platform | Replicable, isolated, scalable operation for multiple businesses | Future; begins only after V0–V6 prove the model |

## Sequencing rules

- Do not pull V2–V7 capabilities into V1 unless they are required for a V1 acceptance criterion.
- Begin V1 implementation only after its own specification is approved.
- Each version gets one durable spec under `specs/` before implementation.
- Each version defines its critical tests; probabilistic behavior also defines evals under `evals/`.
- Reassess the remaining 20-day scope after every completed version rather than widening work in progress.
