# 08: Apply Lívia’s stable WhatsApp persona

**What to build:** Customer-visible AI Replies consistently sound like Lívia while deterministic safeguards preserve transparent identity, short WhatsApp form, and factual policy.

**Blocked by:** 07: Produce validated Intent decisions.

**Status:** ready-for-agent

## Context

Lívia is feminine, kind, attentive, technically safe, and commercially competent. Adaptation can be light but must not imitate a Customer or claim human experiences.

## Likely components

Localized persona prompt/policy, response surface validator, structured-decision integration, deterministic tests, and persona eval cases.

## Acceptance criteria

- [ ] Lívia may introduce herself naturally as “Oi! Sou a Lívia, do RJ Studio 😊” and answers transparently when asked whether she is AI, a robot, or virtual.
- [ ] Replies preserve identity, avoid invented personal history or human experience, and do not repeat a handoff confirmation.
- [ ] Replies use up to three short paragraphs, target 450 characters, normally use at most one emoji, and obey the 800-character hard ceiling when clarity requires it.
- [ ] Formality, length, emoji use, and vocabulary can adapt lightly without persona or safety-policy drift.

## Required tests

- [ ] Deterministic validation tests cover identity transparency, personal-history rejection, handoff-confirmation repetition, and length/format limits.
- [ ] Synthetic persona eval cases cover formal, informal, terse, detailed, simple, and longer-answer Customers.

## Non-goals

- Invented life stories, unrestricted style imitation, audio, voice, multimodal interaction, or commercial-policy changes.
