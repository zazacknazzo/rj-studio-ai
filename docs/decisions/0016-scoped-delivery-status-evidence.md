# Retain scoped delivery evidence and separate conflicts from success

Status: accepted within explicitly authorized offline Ticket 08.

Telnyx early statuses must not enter the legacy provider+Message-only inbox.
Use an append-only minimal receipt ledger with immutable Message scope, durable
event identity and atomic reconciliation at Provider Acceptance. Keep the legacy
inbox untouched so its unscoped rows cannot become Telnyx delivery evidence.

For Telnyx, replace the legacy failure-has-highest-rank policy with independent
success and failure evidence: delivered/read survives a contradictory failure,
while a persistent conflict blocks further automation and requires explicit future
recovery. Failure before delivered/read converges to the same result as failure
after it. Keeping only the strongest success would hide real failures; keeping
only failed would erase confirmed receipt. Meta/Twilio retain their legacy policy.

Minimal evidence contains private routing identifiers, never content or raw error
strings. It survives Message purge and has no automatic expiry until CX-01 defines
retention and safe erasure. No status authorizes sending or resolves unknown by retry.
