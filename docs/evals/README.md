# Evals

V0 is deterministic and is verified by automated tests. Starting with V1, each probabilistic suite lives under `docs/evals/V<N>/`, with a `README.md` as its case index and run record. Executable fixtures may use the format selected by that version's approved spec.

| Version | Status |
| --- | --- |
| V0 | Not applicable; deterministic tests only |
| V1 | Not created; waits for the approved V1 spec |

Each eval case should contain:

- a stable identifier and the spec requirement it protects;
- the Customer scenario and only the minimum approved context needed;
- expected facts, allowed behavior, forbidden claims, and Human Handoff conditions;
- a deterministic assertion or a concise scoring rubric;
- an acceptance threshold and the model/configuration used for the run.

Rules:

- Use synthetic or explicitly sanitized data; never copy real Customer conversations here.
- Add a regression case for every confirmed hallucination or unsafe response.
- Evaluate factual grounding, tone stability, Intent handling, uncertainty, and handoff separately where possible.
- Keep prompts and implementation out of the expected answer so evals survive refactors.
- Evals complement deterministic tests; they do not replace webhook, persistence, adapter, or failure-path tests.

Create the first suite with the approved V1 spec. No V1 eval cases exist yet.
