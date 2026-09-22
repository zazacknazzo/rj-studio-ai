# 02: Enforce the SQLite durability gate

**Status:** ready-for-agent

## Objective

Make SQLite configuration explicit and verifiable before any webhook can use
early acknowledgement.

## Invariants

- A successful future ingress acknowledgement means the inbound commit is on persistent local storage under the configured durability policy.
- Every runtime and migration connection enforces foreign keys and the same busy timeout.
- One application process owns the database.
- No transaction is extended around external work.

## Dependencies

- 01: Separate provider ingress acknowledgement from outbound submission.

## Exact scope

- Apply and verify `journal_mode=WAL` outside write transactions.
- Apply and verify `synchronous=FULL`, `foreign_keys=ON`, and one uniform `busy_timeout` on all runtime connections.
- Apply the required connection configuration to Alembic/migration connections.
- Validate that the configured database is a file on an explicitly configured persistent local directory, not memory or a temporary default.
- Document and validate the single-process deployment invariant to the degree observable by application configuration.
- Extend readiness to reject observable pragma, database-path, schema, or configuration mismatch.
- Audit current generation/order indexes and add only missing indexes supported by measured claim queries.

## Out of scope

- Early ACK, executors, delivery schema, Postgres, multi-process coordination, filesystem durability guarantees the application cannot observe, or performance tuning without evidence.

## Migrations

- Add an Alembic revision only if an existing-table index is required. PRAGMA configuration is not represented as a fake schema migration.

## Required tests

- Fresh database and migrated V0.1/V1 database report required pragmas on runtime and migration connections.
- Readiness fails independently for wrong journal mode, synchronous level, foreign keys, busy timeout, non-persistent path declaration, and schema mismatch.
- Concurrent short writes exercise busy timeout without holding a transaction during generation.
- Existing migration fixtures retain every row.

## Crash cases

- Crash after a committed write must leave the database readable with the committed row present.
- Crash or failure while applying/verifying WAL must keep readiness false; early ACK remains disabled.
- A locked database must fail readiness or the operation within its bounded timeout rather than hang.

## Definition of Done

- Required pragmas are uniformly applied and introspected.
- Readiness exposes every observable violation with a safe error code.
- Deployment documentation states persistent local storage and one process.
- Full tests, migration tests, Ruff, and existing static checks pass.

## Rollout and rollback

- Deploy before enabling any early-ACK mode.
- Verify the real deployment volume and readiness after restart.
- Rollback retains a readable SQLite database; do not switch journal mode while another process is active.
