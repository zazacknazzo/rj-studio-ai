# Ticket 13 — independent Security/Reliability final review

Date: 22/11/2026, America/Sao_Paulo. Candidate inspected and tested:
`995af20ff7d9e9f592a23c544f09a2407bd1b7f0`, branch
`codex/telnyx-coexistence-13-readiness`. Repository status was clean at completion.
Reviewer had read-only repository access by instruction; all authored probes and
this report are outside the repository. No commit or push by this reviewer.

**Assessment: PASS for the authorized offline preparation scope; no new confirmed
P1/P2 pending in the inspected candidate. AUD-01 remains OPEN. Pilot, external
controlled operation and production remain NO-GO.** This is not approval of release
or infrastructure security.

## Evidence independently executed

| Execution | Actual result |
| --- | --- |
| Own 15 recovery adversarial probes plus nine fresh-child network guard tests | **24 passed, 16.57 seconds, exit 0** |
| Gitleaks 8.30.1 scan of candidate `git archive HEAD` materialized outside repository | **3 raw findings, exit 1**, all unchanged baseline false positives |
| Candidate triage script against that independently generated report | **PASS, exit 0**, file/line/rule and entire-file SHA256 match for all three findings |
| Gitleaks 8.30.1 range `f1496be42732b7e57d317444d7ed0020997f0327..995af20ff7d9e9f592a23c544f09a2407bd1b7f0` | **7 commits, 0 findings, exit 0** |

Test command from repository root:

```sh
../venv/bin/python scripts/check_telnyx_offline.py --python ../venv/bin/python --output ../review-security/final-probes ../review-security/test_security_recovery_probes.py tests/test_offline_network_guard.py
```

Own test source remains `work/review-security/test_security_recovery_probes.py`;
JUnit evidence is `work/review-security/final-probes/pytest.xml`. Environment:
CPython 3.14.7, SQLite 3.50.4, pytest 9.2.0, macOS arm64. Private temporary
directories, sanitized environment, synthetic data and no real Telnyx calls.

Own recovery probes cover authority restore after access revocation of four roles
before the application observes it, source/witness unavailability without cached
permission, failed witness write rolling back mutation, witness advancement followed
by authority commit failure, concurrent revoke versus reservation, verifier-only
reconciliation proof, expiry at the exact boundary through the alternate reservation
entrypoint, and cross-intent submission-key reuse. All passed on the final candidate.
The nine guard tests independently create child Python processes and prove denial
for IPv4/IPv6 TCP/UDP, DNS resolution APIs and sendmsg.

Secret-scan commands were run using `work/tools/gitleaks` against
`work/review-security/final-secret-source` and the repository commit range. The
redacted tree report is `work/review-security/final-gitleaks.json`. I inspected the
three contexts: public OpenAPI hash in the T11 report, evaluation configuration
prose, and an explicitly synthetic operator credential fixture. No new ignore file
or rule exclusion was introduced. This is three raw detections, not zero tree hits.

Earlier independent executions, not added to the final count: baseline **214 passed
in 11.96s** and CP2 own probes **15 passed in 7.88s**. These overlap later coverage;
do not sum them as unique tests. I did not reexecute the full 2,262-case suite.

## Direct code and document assessment

The recovery module remains a protocol laboratory with no sender, transport callback,
commercial adapter, public release endpoint, release CLI or production selector.
Even simulation release retains the explicitly quarantined store. Authority/witness
reads are challenge-bound and uncached; rollback within the same epoch, same-revision
equivocation, current proof changes and source failure deny recovery. Independent
inventory reservation validates current proofs, TTL and reconciled inventory inside
its CAS mutation, closing the read-to-reservation expiry window. Previous work remains
blocked by stable intent/key even after reconciliation. Witness-before-authority
commit failure conservatively prevents accepting the prior authority state.

I inspected the final workflow, scripts, pinned versions, network guard, security/
consent specification, recovery runbook and operational runbooks. Role segregation,
separate approver/recoverer, access revocation, scoped/current proof, opt-out ordering,
the authorization-to-HTTP race, unsupported 422 behavior and emergency stop are
described with explicit external gates. The documents correctly say that current
consent capture/audit, enterprise IAM, mobile operator workflow and real account
verification remain unimplemented. No false claim of complete LGPD compliance.

The workflow pins action SHAs, sets contents:read, disables persisted checkout
credentials and uses no commercial secret reference. Tool installation/advisory
queries occur before a Linux network namespace. The checks execute as the runner
user after `unshare --net`; the assertion permits only loopback and no IPv4/IPv6
default route. The strengthened Python guard separately blocks DNS/socket APIs and
is inherited by children. I executed the Python guard evidence on macOS; I did not
independently execute the Linux namespace or claim a completed remote workflow.

`requirements/ci.lock` pins 86 distributions, including build/audit tools. I inspected
the supplied audit JSON: **87 total entries, zero advisories, one explicitly skipped
unindexed local application**. I did not execute that online advisory query myself.
Versions are pinned without wheel hashes and are explicitly not presented as a
universal artifact/platform lock. The lock header still mentioned Linux 3.14 despite
the workflow selecting only 3.12; the primary writer already identified this
documentary mismatch and announced correction without changing pins. This does not
alter the security assessment or justify claiming Linux 3.14 validation.

## Exact inspected hashes

| File | SHA256 |
| --- | --- |
| `src/rj_studio_ai/offline_recovery.py` | `6d50cfc82a436320c7310185f0f6070347c0e42599876bb7ebef7b76f5166a9c` |
| `tests/offline_recovery_fixture.py` | `cf9850f15716475e55ca7608602609dd4e4077d94b1a42d2ca37461c863d3eb4` |
| `scripts/check_telnyx_offline.py` | `bc6844c979db12571818e69322219af1aeb4e54983f9b0d8cdbf97f754d90ed6` |
| `.github/workflows/telnyx-offline.yml` | `27c3d9d41f0f44221c55b8a0af055304a719ac3e8cf9125c3c564c6f9ce186cd` |
| `requirements/ci.lock` before the announced comment-only correction | `38442a4f79b797bcbb1148ec29e004ee49b8196bcd43a6a6f8bddbde5c49e051` |

## Remaining operational limits

No proof here of authenticated remote authority responses, storage linearizability,
independent administration/backups, IAM/TLS, complete ledger coverage of every future
HTTP path, physical durability, current real consent, real account binding/sync,
operator drill or proxy/network latency. Rollback of every trust root together is
not detectable using only those rolled-back roots. The generic historical store is
not protected by this offline laboratory when composed outside quarantine.

No real credential, account, activation, release, pilot or Telnyx HTTP was used or
authorized. No risk checkbox closed or exception accepted. Direct final orchestrator
audit remains required before any next gate.
