# 05: Load approved Salon Knowledge

**What to build:** RJ Studio can keep versioned YAML Salon Knowledge whose approved, relevant facts and mandatory rules are selected safely for an AI Attendant request.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

## Context

Salon facts must remain localized data, not generic orchestration logic. Technical facts need the specified specialist validation before publication.

## Likely components

Versioned YAML knowledge files, validation and selection module, localized pilot facts, configuration/loading seam, synthetic fixtures, and knowledge tests.

## Acceptance criteria

- [ ] YAML validation requires stable ID, category/topic, publication status, fact type, approvals, review metadata, and source/reference where applicable.
- [ ] Only approved facts are selectable; draft, absent, irrelevant, or insufficiently validated technical facts cannot be surfaced as RJ Studio facts.
- [ ] Selection progressively returns only relevant pilot facts within the input budget, including Service-linked mandatory policies and `requires_human_consultation`.
- [ ] Customer-provided statements cannot create or override Salon Knowledge.

## Required tests

- [ ] Loader/selection tests for approved versus draft, operational versus technical validation, missing metadata, irrelevant facts, and conflicting Customer claims.
- [ ] Synthetic grounding fixtures cover known and unknown price, Professional, Service, policy, and availability questions.

## Non-goals

- CMS approval workflow, vector database, RAG service, broad knowledge ingestion, or a customer-facing administration interface.
