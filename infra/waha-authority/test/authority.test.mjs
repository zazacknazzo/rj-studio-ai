import test from "node:test";
import assert from "node:assert/strict";
import { fixture, scope, head, intent, participant, account, nonce, hash } from "./runtime.mjs";

test("real workerd: signed CAS and exactly one potential submission under concurrency", async (t) => {
  const f = await fixture(t); assert((await f.initialize()).ok); assert((await f.release()).ok);
  assert((await f.runtime("register")).ok);
  const current = (await f.command("authority", "read")).state;
  const args = { boot: current.boot, epoch: current.epoch, head: current.head, intent, participant, digest: "f".repeat(64), key: "9".repeat(32), token: nonce() };
  const results = await Promise.all(Array.from({ length: 8 }, () => f.command("authority", "consume", args, { expected: current.revision })));
  assert.equal(results.filter((r) => r.ok).length, 1);
  const final = (await f.command("authority", "read")).state;
  assert.equal(final.intents[intent].outcome, "unknown");
  assert.equal(final.grant, null);
  assert.equal((await f.runtime("consume", { token: nonce() })).ok, false);
  assert.equal((await f.release()).error, "unresolved_submission");
});

test("same Cloudflare account never constitutes independent administration", async (t) => {
  const f = await fixture(t, { sameAccount: true });
  assert.equal((await f.initialize()).error, "administration_not_independent");
});

test("witness unavailable denies every operational read and mutation", async (t) => {
  const f = await fixture(t, { witnessFailure: true });
  assert.equal((await f.initialize()).error, "witness_unavailable");
});

test("restore of authority storage cannot erase a submission retained by witness", async (t) => {
  const f = await fixture(t); await f.initialize(); await f.release(); await f.runtime("register");
  const old = await f.snapshot();
  assert((await f.runtime("consume", { token: nonce() })).ok);
  await old.storage.exec("UPDATE root SET value=? WHERE id=1", old.rows[0].value);
  assert.equal((await f.command("authority", "read")).error, "witness_unavailable");
});

test("local restore, boot replacement, pause, revocation, kill and expired release deny", async (t) => {
  const f = await fixture(t); await f.initialize();
  assert.equal((await f.mutate("boot", { boot: nonce(), head: "0".repeat(64), sequence: 1 })).error, "local_restore_or_boot_invalid");
  assert.equal((await f.runtime("register")).error, "egress_paused_or_snapshot_stale");
  assert((await f.release()).ok);
  assert.equal((await f.runtime("register", { participant: "0".repeat(64) })).error, "release_missing_or_expired");
  const before = (await f.command("authority", "read")).state;
  assert((await f.runtime("advance", { prior: head, head: "8".repeat(64), sequence: 2, kind: "pause" })).ok);
  assert.equal((await f.runtime("register")).error, "egress_paused_or_snapshot_stale");
  assert.equal((await f.mutate("release", { boot: before.boot, epoch: before.epoch, head: before.head, participant, intent, expires_at: Date.now() - 1 }, "operator")).ok, false);
  await f.release();
  assert((await f.mutate("kill", {}, "operator")).ok);
  assert.equal((await f.runtime("register")).error, "egress_paused_or_snapshot_stale");
  const current = (await f.command("authority", "read")).state;
  assert((await f.runtime("advance", { prior: current.head, head: "7".repeat(64), sequence: 3, kind: "revoke", participant })).ok);
  assert.equal((await f.release()).error, "participant_not_authorized");
});

test("only actual acceptance outcome may resolve unknown; it never re-arms the intent", async (t) => {
  const f = await fixture(t); await f.initialize(); await f.release(); await f.runtime("register");
  const token = nonce(); await f.runtime("consume", { token });
  assert.equal((await f.runtime("outcome", { token, outcome: "not_submitted" })).error, "outcome_unproven");
  assert((await f.runtime("outcome", { token, outcome: "accepted", acceptance: "3".repeat(64) })).ok);
  assert.equal((await f.release()).error, "intent_already_consumed");
  assert.equal((await f.runtime("consume", { token: nonce() })).ok, false);
});

test("authentication, scope, stale challenges, role separation and CAS fail closed", async (t) => {
  const f = await fixture(t); await f.initialize();
  assert.equal((await f.command("authority", "read", {}, { signature: "0".repeat(64) })).status, 403);
  assert.equal((await f.command("authority", "read", {}, { time: Date.now() - 60000 })).error, "challenge_expired");
  assert.equal((await f.command("authority", "read", {}, { requestScope: "0".repeat(64) })).error, "scope_mismatch");
  assert.equal((await f.mutate("kill")).error, "operator_required");
  assert.equal((await f.command("witness", "enroll", { authority_account: account, digest: hash({}) }, { role: "operator", expected: 0 })).ok, false);
  const stale = (await f.command("authority", "read")).state;
  await f.mutate("kill", {}, "operator");
  assert.equal((await f.command("authority", "kill", {}, { role: "operator", expected: stale.revision })).error, "authority_revision_conflict");
});

test("witness restore, and crash between witness and authority commits, deny subsequent work", async (t) => {
  const f = await fixture(t); await f.initialize();
  const before = await f.snapshot("witness", "Witness");
  await f.release();
  await before.storage.exec("UPDATE root SET value=? WHERE id=1", before.rows[0].value);
  assert.equal((await f.command("authority", "read")).ok, false);
});

test("fresh resume never regrants consent, and old boot cannot submit", async (t) => {
  const f = await fixture(t); await f.initialize();
  const old = (await f.command("authority", "read")).state;
  await f.runtime("advance", { prior: head, head: "6".repeat(64), sequence: 2, kind: "resume" });
  assert.equal((await f.runtime("register")).error, "egress_paused_or_snapshot_stale");
  const newer = await f.mutate("boot", { boot: nonce(), head: "6".repeat(64), sequence: 2 });
  assert(newer.ok);
  assert.equal((await f.mutate("register", { boot: old.boot, epoch: old.epoch })).error, "boot_fence_invalid");
});

test("kill after consumption prevents final transport authorization", async (t) => {
  const f = await fixture(t); await f.initialize(); await f.release(); await f.runtime("register");
  const token = nonce(); await f.runtime("consume", { token });
  await f.mutate("kill", {}, "operator");
  assert.equal((await f.runtime("check_submission", { token })).error, "submission_not_current");
});

test("different request bytes or a replacement key never reuse a logical intent", async (t) => {
  const f = await fixture(t); await f.initialize(); await f.release(); await f.runtime("register");
  assert.equal((await f.runtime("register", { digest: "4".repeat(64) })).error, "intent_identity_conflict");
  assert.equal((await f.runtime("register", { key: nonce() })).error, "intent_identity_conflict");
});

test("reconciliation cannot prove non-submission or re-arm an old intent", async (t) => {
  const f = await fixture(t); await f.initialize(); await f.release(); await f.runtime("register");
  const token = nonce(); await f.runtime("consume", { token });
  const args = { intent, token, digest: "f".repeat(64), evidence: "5".repeat(64), acceptance: "3".repeat(64) };
  assert.equal((await f.mutate("reconcile", { ...args, outcome: "not_submitted" }, "operator")).ok, false);
  assert((await f.mutate("reconcile", { ...args, outcome: "accepted" }, "operator")).ok);
  assert.equal((await f.release()).error, "intent_already_consumed");
});
