# Ticket 06 — validation and independent audit

Delivery record: 2026-11-11. Scope: approved Ticket 06 only.
Base: `7d597acc20bda937b708c53ef2fa54427fec5109`
(`codex/telnyx-coexistence-05-admin`). Reviewed implementation:
`b5e0ea69fb8b3e70217a614bde01dcc07857bf81`.
Branch: `codex/telnyx-coexistence-06-auth`.

## Result

Dormant Telnyx webhook authentication validates original request bytes with
Ed25519, timestamp tolerance and expected scope. Configuration, body size,
headers, key encoding/curve validity and malformed JSON fail closed with safe
errors. No canonical Message/echo/status/lifecycle parsing, route, ACK, sender,
readiness enablement or operational effects were added. The runtime still rejects
Telnyx as a selectable provider. Bearer administration remains separate.

The public point is validated by libsodium before PyNaCl signature verification.
Production dependency is pinned to PyNaCl 1.6.2; cryptography 50.0.2 is a dev-only
independent test signer. Trusted key provenance and use of the patched bundled
libsodium are deployment requirements. See the [spec](../specs/V1-telnyx-coexistence-ticket-06.md)
for official sources, scope rules, parameters and limits.

## Checks

- Full offline pytest after correction: **1482 passed, 1 skipped** in 71.68 seconds,
  including **114 Ticket 06 cases**.
- The skip is the preexisting `test_historical_v8_record_remains_loadable` in
  `tests/test_commercial_steering.py`: local history evidence is not checked into
  Git. No authentication or provider compatibility test was skipped.
- `ruff check .`, `ruff format --check .` (266 Python files),
  `python -m compileall -q src tests`, `python -m pip check` and
  `git diff --check` passed.
- Tests used an isolated virtual environment, minimal process environment,
  synthetic inputs and temporary SQLite. An inherited Python `sitecustomize`
  audit hook rejected IPv4/IPv6 `socket.connect` and `socket.sendto`, including
  child Python processes. No commercial .env or customer database was used.
- Only the authorized files below differ from baseline. Meta/Twilio adapters,
  neutral contracts, persistence/migrations, outbox, processing, administrative
  operations and intelligence files are byte-identical to Ticket 05.
- The separate Baileys worktree retained its HEAD, status and hashes of all 272
  tracked files. Local main remained unchanged; remote main was confirmed at
  `af1c9eb862a4180ca6b9e537349e4f8abaa2bb29`, and Ticket 05 at the approved base.

The first full run passed 1475 tests before review. The weak-key finding below
led to seven additional regressions and a corrected verifier before the final
complete run. No runtime code changed after that final run.

## Required test coverage

All new cases are in `tests/test_telnyx_authentication.py`.

| Requirement | Evidence |
| --- | --- |
| Synthetic Ed25519 and original whitespace/Unicode bytes | `test_valid_ed25519_returns_exact_bytes_without_canonical_parsing` |
| Invalid/missing/tampered signature | `test_invalid_signature`, `test_missing_authentication_header`, `test_wrong_public_key_and_tampered_timestamp` |
| Modified body and wrong signing construction | `test_altered_body_fails_even_when_json_is_equivalent`, `test_signature_over_body_without_timestamp_prefix_is_rejected` |
| Expired/future/missing/invalid timestamp | `test_invalid_or_stale_timestamp_fails_with_real_signature`, `test_signature_window_includes_both_boundaries`, `test_invalid_clock_fails_closed` |
| Missing/malformed/degenerate key and configuration | `test_incomplete_invalid_or_mutated_configuration_fails_closed`, `test_invalid_curve_keys_reject_forgery_before_authentication`, `test_unavailable_point_validation_fails_closed` |
| Authentication before JSON inspection; byte size cap | `test_authentication_precedes_any_json_inspection`, `test_body_limit_counts_bytes_before_parsing` |
| Repeated delivery and old event freshly signed | `test_custom_window_and_fresh_signature_on_old_event` |
| Wrong or missing channel/profile/WABA | message scope, outbound sender scope, lifecycle scope and contradictory-scope tests |
| No unauthenticated effects or partial send readiness | `test_http_has_no_telnyx_route_or_operational_effects`, `test_telnyx_cannot_be_selected_in_runtime` |
| Privacy and administrative separation | `test_settings_errors_and_logs_never_expose_private_values`, `test_invalid_environment_limits_are_redacted`, `test_bearer_never_substitutes_for_ed25519` |
| Tickets 01–05 compatibility | Existing contracts, journal, pause, outbound fencing, operations and Meta/Twilio suites passed |

## Standards review

Independent reviewer initially reported **one P2**: length-only Ed25519 key import
accepted degenerate public points, including an identity point under which a forged
signature authenticated arbitrary fresh, scoped content. This violated fail-closed
configuration requirements. No other documented-standard violation or actionable
code smell was found.

The correction replaced the production verifier with pinned PyNaCl and validates
public points with libsodium. The reviewer independently reran all **114 focused
tests with IP networking blocked**, reproduced rejection of both original forgery
keys, and cleared the final baseline diff at `b5e0ea6`: **no remaining P1/P2**.

## Spec review

A separate reviewer independently reproduced the same **P2**. No other missing
requirement, scope expansion or incorrect behavior was found. After correction,
this reviewer ran **12 relevant synthetic regressions with IP networking disabled**
and cleared the final implementation at `b5e0ea6`: **no remaining P1/P2**.

The two axes each found one instance of the same underlying defect; both cleared
it after correction. Scope-only inspection, temporal replay without deduplication,
original-byte verification and dormant runtime match the authorized slice.

## Secret and privacy audit

Gitleaks 8.30.1 scanned every new commit since Ticket 05 with fully redacted
reports. One finding was manually classified as a false positive: the explicitly
synthetic operator-secret fixture in `tests/test_telnyx_authentication.py:32`,
introduced in `8bccd98`. It is test-only text, not a commercial credential. A rerun
with only that exact historical fingerprint excluded reported no leaks. No broad
rule, file or directory was excluded. No repository scanner bypass was added.

Manual review and the authorized-file allowlist found no real credential, customer
data, private key, database or commercial .env. Runtime privacy tests captured logs,
errors, tracebacks, Settings repr and serialized values. Synthetic private values
were absent from those surfaces. The new authenticator emits no logs.

## Files changed

- `.env.example`: empty dormant ingress settings and runtime restriction.
- `pyproject.toml`: pinned verifier and independent dev-only signer.
- `src/rj_studio_ai/config.py`: redacted scope/key settings and bounded limits.
- `src/rj_studio_ai/providers/telnyx.py`: raw-byte authentication and scope boundary.
- `tests/test_telnyx_authentication.py`: synthetic acceptance/security regressions.
- `docs/specs/V1-telnyx-coexistence-ticket-06.md`: authorized scope and sources.
- `docs/specs/README.md`: spec index entry.
- `docs/decisions/0014-telnyx-webhook-authentication.md`: boundary decision.
- `.scratch/telnyx-coexistence/issues/06-authentication.md`: ticket state.
- `docs/architecture/v1-ticket06-validation.md`: this validation/audit record.

## Residual limits and Ticket 07 handoff

Authentication is validated offline; production integration is not validated.
No number, Telnyx account, webhook configuration, API key, message or credit was
used. Signatures can repeat inside the replay window by design; downstream durable
deduplication remains necessary. Event timestamps and channel availability are not
inferred from signature freshness.

Ticket 07 can build on this boundary only after direct GitHub audit and explicit
user authorization. It must validate semantic inbound/echo contracts and commit
durable effects before ACK. Full HTTP composition must preserve raw bytes, reject
duplicate raw authentication headers before dictionary conversion, and enforce the
body cap while streaming. A blocked channel must still permit operational ingress
once that composition exists. None of this later work began.

Trusted public-key provisioning, synchronized clocks and patched bundled libsodium
remain required. Existing journal retention holds, echo best-effort and the
submission-marker-to-HTTP race are unchanged. This delivery does not claim
production readiness or authorization for Tickets 07–13.
