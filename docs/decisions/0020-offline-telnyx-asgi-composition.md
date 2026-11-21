# Bound raw HTTP ingress without granting operational readiness

Status: accepted within explicitly authorized offline Ticket12 scope, 2026-11-21.

Keep the ASGI factory isolated from production composition. Preserve raw headers until
ambiguity checks, stream original bytes with actual-length/time limits, authenticate
before parsing, and commit canonical events/effects before ACK. Use1.35s work/1.5s total
budget, including SQLite wait/commit and final check; late commits remain replay-safe.
Application code cannot hard-preempt fsync or server backpressure; no live SLA is claimed.

Revalidate CX29 by retaining conservative non2xx rejection for unsupported contracts.
Persist only bounded aggregate rejection observations, never raw content/IDs/body hashes
in the operational journal. These counters diagnose retries without pretending unsupported
Messages were handled or granting success. No automatic fallback, generation or retry.
This refines ADR0014–17's deferred HTTP policy without widening supported wire contracts.

Quarantine is structural and outside SQLite: the offline composition has no workers,
sender or release capability. Strict request binding is required for Telnyx authorization
in its store; legacy internal compatibility remains outside that composition. Restoring
an active row cannot enable it. This is not complete operational recovery: independent
freshness, reconciliation and authenticated release require future infrastructure and
explicit authorization. AUD01 stays open. No unknown deletion, new keys or old replay.

Separate six readiness dimensions; health/ingress does not imply a sendable channel.
Keep labels finite and privacy-safe. Real account, operator workflow, retention/erase,
key/clock provisioning, subscription behavior, CI and operational acceptance remain gates.
