# Conversational initiative without model authority over facts or state

Status: proposed

The [V1 Agentic Boundary Review](../architecture/v1-agentic-boundary-review.md)
recommends evolving the existing structured decision/finalizer seam into a
single-call plan plus constrained composer. The model would choose conversational
acts, question targets, timing and permitted wording; the core would authorize
facts/actions/terminal handoff, enforce durable limits and render protected
segments before atomic completion. This avoids tying all conversational quality
to phrase IDs without introducing a second LLM or messaging redesign.

Trusted slots cannot prove that unrestricted surrounding prose contains no
unapproved factual claim. Start with model-selected acts and controlled surfaces;
any wider generative wording requires explicit approval of its representation,
tests and residual semantic risk. Current ADRs 0007/0008 and approved specs remain
in force. This proposal authorizes no runtime, prompt, oracle or migration change;
Phase B is paused and Ticket 12 remains in-progress.

## Phase 1 evidence — 2026-10-04

Separate product-owner approval authorized the
[Phase 1 experiment](../specs/V1-agentic-surface-phase-1.md). Its
[implementation report](../architecture/v1-agentic-surface-phase-1.md) records
the wider generative representation and retained factual/state authority. That
approval supersedes the earlier no-change scope for this experiment only. It
does not accept this ADR, approve pilot or resume Phase B. Historical evidence
is unchanged; new oracles are versioned.

Phase 1 evidence: 890 offline tests and four independent reviews passed. The
[new smoke](../evals/V1/agentic-surface-smoke-2026-10-04.md) passed ten functional
cases (0/19 critical failures); p95 observed E2E 10.930s failed the official 8s
gate. Qualitative human review is pending, including two generic fallbacks.
Status remains proposed; no universal free-prose semantic guarantee is claimed.
