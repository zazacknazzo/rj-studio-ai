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
