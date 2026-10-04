# V1 agentic eval classification

Oracle: `v1-agentic-behavioral-2026-10-04-v3`. Historical runs retain v2 scores/evidence.

All 53 IDs audited. Primary contracts: DETERMINISTIC_ADVERSARIAL: 5, LIVE_BEHAVIORAL: 45, STRUCTURAL_CONTRACT: 3.

Five counterfactual model-plan scenarios require deterministic injection. Their paid counterparts observe actual behavior without injecting a proposal or preferences. The live scheduler therefore retains 50 behavioral scenarios plus three structural contracts, without claiming a benign live plan proves invalid-plan rejection.

| Case | Primary contract | Live execution |
| --- | --- | --- |
| `intent-greeting` | LIVE_BEHAVIORAL | Behavioral |
| `intent-service-information` | LIVE_BEHAVIORAL | Behavioral |
| `intent-price` | LIVE_BEHAVIORAL | Behavioral |
| `intent-professional` | LIVE_BEHAVIORAL | Behavioral |
| `intent-hours` | LIVE_BEHAVIORAL | Behavioral |
| `intent-location` | LIVE_BEHAVIORAL | Behavioral |
| `intent-technical-guidance` | LIVE_BEHAVIORAL | Behavioral |
| `intent-appointment-interest` | LIVE_BEHAVIORAL | Behavioral |
| `intent-appointment-change` | LIVE_BEHAVIORAL | Behavioral |
| `intent-complaint` | LIVE_BEHAVIORAL | Behavioral |
| `intent-promotion` | LIVE_BEHAVIORAL | Behavioral |
| `intent-human-request` | LIVE_BEHAVIORAL | Behavioral |
| `intent-other` | LIVE_BEHAVIORAL | Behavioral |
| `intent-price-and-appointment` | LIVE_BEHAVIORAL | Behavioral |
| `persona-formal` | LIVE_BEHAVIORAL | Behavioral |
| `persona-informal` | LIVE_BEHAVIORAL | Behavioral |
| `persona-terse` | LIVE_BEHAVIORAL | Behavioral |
| `persona-detailed` | LIVE_BEHAVIORAL | Behavioral |
| `persona-identity` | LIVE_BEHAVIORAL | Behavioral |
| `persona-incomplete-context` | LIVE_BEHAVIORAL | Behavioral |
| `grounding-divergent-price` | DETERMINISTIC_ADVERSARIAL | Behavioral counterpart |
| `grounding-false-customer-fact-and-injection` | LIVE_BEHAVIORAL | Behavioral |
| `grounding-explicit-service-and-injection` | LIVE_BEHAVIORAL | Behavioral |
| `grounding-unknown-price` | LIVE_BEHAVIORAL | Behavioral |
| `grounding-unknown-hours` | LIVE_BEHAVIORAL | Behavioral |
| `grounding-unauthorized-discount` | LIVE_BEHAVIORAL | Behavioral |
| `grounding-invalid-reference` | DETERMINISTIC_ADVERSARIAL | Behavioral counterpart |
| `grounding-multiple-facts` | LIVE_BEHAVIORAL | Behavioral |
| `grounding-outside-knowledge` | LIVE_BEHAVIORAL | Behavioral |
| `grounding-technical-risk` | LIVE_BEHAVIORAL | Behavioral |
| `grounding-required-consultation` | LIVE_BEHAVIORAL | Behavioral |
| `grounding-mandatory-policy` | LIVE_BEHAVIORAL | Behavioral |
| `grounding-explicit-human-request` | LIVE_BEHAVIORAL | Behavioral |
| `appointment-complete` | LIVE_BEHAVIORAL | Behavioral |
| `appointment-missing-service` | LIVE_BEHAVIORAL | Behavioral |
| `appointment-missing-time` | LIVE_BEHAVIORAL | Behavioral |
| `appointment-optional-professional` | LIVE_BEHAVIORAL | Behavioral |
| `appointment-change` | LIVE_BEHAVIORAL | Behavioral |
| `appointment-cancellation` | LIVE_BEHAVIORAL | Behavioral |
| `appointment-reschedule` | LIVE_BEHAVIORAL | Behavioral |
| `appointment-model-availability-promise` | DETERMINISTIC_ADVERSARIAL | Behavioral counterpart |
| `appointment-model-booking-confirmation` | DETERMINISTIC_ADVERSARIAL | Behavioral counterpart |
| `appointment-two-questions-exhausted` | LIVE_BEHAVIORAL | Behavioral |
| `appointment-short-answers` | LIVE_BEHAVIORAL | Behavioral |
| `appointment-invented-preferences` | DETERMINISTIC_ADVERSARIAL | Behavioral counterpart |
| `appointment-injection-cannot-confirm` | LIVE_BEHAVIORAL | Behavioral |
| `handoff-technical-risk` | LIVE_BEHAVIORAL | Behavioral |
| `handoff-human-request` | LIVE_BEHAVIORAL | Behavioral |
| `handoff-serious-complaint` | LIVE_BEHAVIORAL | Behavioral |
| `handoff-explicit-release` | LIVE_BEHAVIORAL | Behavioral |
| `context-bounded-history` | STRUCTURAL_CONTRACT | No LLM |
| `context-return-after-days` | STRUCTURAL_CONTRACT | No LLM |
| `context-pending-not-speech` | STRUCTURAL_CONTRACT | No LLM |

## Coupling removed

Approved statements/qualifiers remain exact-source checks. Residual prose no longer needs to match ReplyPhrase catalog wording. Case 32 accepts safe missing-preference questions with different wording. Appointment checks compare persisted counters/preferences/recovery and terminal reasons with observed authorized targets and synthetic source evidence, not a fixed question sequence. Persona protects identity/hard bounds; qualitative naturalness stays human-owned.

Structural contracts test context bounds/expiry/delivery visibility without generation. Offline injection retains adversarial contracts. Future oracle/record versions identify new runs. YAML cases and historical work/evals are unchanged; no historical rescore.
