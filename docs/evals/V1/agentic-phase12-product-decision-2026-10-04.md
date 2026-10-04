# Agentic Surface Phase 1.2 — product-owner decision

Human review: **PASS WITH NOTES**.

Recorded 2026-10-04 from the product owner's explicit instruction. Reviewed
baseline: `c83c7d83ca543366f8348e4d6278c009b3e3ae9e`; the
[Phase 1.2 evidence](agentic-phase12-results-2026-10-04.md) remains unchanged.

Freeze conversational quality for now. Minor wording imperfections in cases 4
and 9 do not authorize prompt/surface changes, new deterministic rules, fixed
phrases, ReplyPhrase changes or commercial steering changes. The current agentic
architecture is approved to proceed to runtime evaluation. This is not pilot
approval, a latency pass or completion of Ticket 12.

The [qualitative packet](agentic-phase12-human-review-2026-10-04.md) retains all ten
original responses. Blank worksheet questions remain blank; no numerical notes
or automatic naturalness scores are inferred from this decision. Private run
artifacts retain their status at collection time, without rescore or relabeling.

## Runtime reasoning-effort A/B — budget preflight stopped

Requested experiment: the same ten synthetic cases, medium versus low, one
generation each, ideally interleaved; shared US$0.30 hard cap. Only reasoning
effort may vary. Model gpt-6.1-sol, default tier, ceiling 1024, observation 30s,
prompt/Knowledge/scorer/authority remain fixed; zero retries, no real messaging
or Anthropic, and Phase B stays paused.

The latest ten-case smoke consumed US$0.0420408. Doubling its observed usage
projects **US$0.0840816** for twenty calls, but this is not a spending guarantee.
Its ten worst-case reservations total US$0.2052350: the existing harness uses
counted input plus its unchanged 1024-token input allowance, worst-case input
rate and the full 1024-token output ceiling. Doubling them projects
**US$0.4104700**, above US$0.30. No cached-input discount is assumed in a reserve.

Apply the user's instruction to stop before execution if the projected cap
cannot accommodate twenty calls, using this conservative reservation projection.
The expected consumption fits; the twenty-call ceiling does not. This does not
claim that actual usage would exceed US$0.30. Existing per-call enforcement could
stop a run early while keeping that cap, but cannot guarantee all twenty samples.

No calls, preflight API requests, credentials access, harness/configuration or
runtime changes were performed. Medium/low metrics and comparison packets do
not exist for this experiment. Recommendation: **INCONCLUSIVE**, no new evidence.
Do not reuse Phase 1.2 replies as A/B samples. An explicit budget interpretation
or higher cap is needed before execution; the agent does not raise the cap or
reduce headroom. Ticket 12 remains in-progress; operational/latency gates remain.
