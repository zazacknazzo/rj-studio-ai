import { DurableObject } from "cloudflare:workers";

const encoder = new TextEncoder();
const hex = (bytes) => [...new Uint8Array(bytes)].map((v) => v.toString(16).padStart(2, "0")).join("");
const validHash = (v) => typeof v === "string" && /^[a-f0-9]{64}$/.test(v);
const validNonce = (v) => typeof v === "string" && /^[a-f0-9]{32}$/.test(v);
const clone = (value) => JSON.parse(JSON.stringify(value));

export function canonical(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  return `{${Object.keys(value).sort().map((k) => `${JSON.stringify(k)}:${canonical(value[k])}`).join(",")}}`;
}

async function digest(value) {
  return hex(await crypto.subtle.digest("SHA-256", encoder.encode(canonical(value))));
}

async function hmac(key, text) {
  const imported = await crypto.subtle.importKey("raw", encoder.encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return hex(await crypto.subtle.sign("HMAC", imported, encoder.encode(text)));
}

function equal(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let difference = 0;
  for (let i = 0; i < a.length; i++) difference |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return difference === 0;
}

class Closed extends Error {
  constructor(code) { super(code); this.code = code; }
}

function requireThat(condition, code) { if (!condition) throw new Closed(code); }

async function sign(env, value) {
  const key = await crypto.subtle.importKey("jwk", JSON.parse(env.SIGNING_JWK), "Ed25519", false, ["sign"]);
  return { payload: value, signature: hex(await crypto.subtle.sign("Ed25519", key, encoder.encode(canonical(value)))) };
}

async function verifySigned(raw, publicKey) {
  requireThat(raw && typeof raw.signature === "string" && /^[a-f0-9]{128}$/.test(raw.signature), "witness_signature_invalid");
  const key = await crypto.subtle.importKey("raw", Uint8Array.from(publicKey.match(/../g).map((v) => parseInt(v, 16))), "Ed25519", false, ["verify"]);
  const signature = Uint8Array.from(raw.signature.match(/../g).map((v) => parseInt(v, 16)));
  requireThat(await crypto.subtle.verify("Ed25519", key, signature, encoder.encode(canonical(raw.payload))), "witness_signature_invalid");
  return raw.payload;
}

async function authenticate(request, env) {
  requireThat(request.method === "POST" && new URL(request.url).pathname === "/command", "request_invalid");
  requireThat(request.headers.get("content-type") === "application/json", "request_invalid");
  const role = request.headers.get("x-livia-role");
  const secret = ({ runtime: env.RUNTIME_KEY, operator: env.OPERATOR_KEY, authority: env.AUTHORITY_KEY })[role];
  requireThat(typeof secret === "string" && secret.length >= 32, "authentication_failed");
  requireThat(Number(request.headers.get("content-length") || 0) <= 32768, "request_too_large");
  const reader = request.body?.getReader();
  requireThat(reader, "request_invalid");
  let size = 0; const chunks = [];
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.length;
    requireThat(size <= 32768, "request_too_large");
    chunks.push(value);
  }
  const bytes = new Uint8Array(size); let position = 0;
  for (const chunk of chunks) { bytes.set(chunk, position); position += chunk.length; }
  const body = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  requireThat(equal(await hmac(secret, body), request.headers.get("x-livia-signature")), "authentication_failed");
  const command = JSON.parse(body);
  requireThat(body === canonical(command), "noncanonical_request");
  requireThat(command.v === 1 && command.scope === env.SCOPE && validHash(env.SCOPE), "scope_mismatch");
  requireThat(validNonce(command.nonce) && Number.isSafeInteger(command.time) && Math.abs(Date.now() - command.time) <= 15000, "challenge_expired");
  requireThat(typeof command.action === "string" && command.args && typeof command.args === "object" && !Array.isArray(command.args), "request_invalid");
  return { ...command, role };
}

function response(value, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
}

class SignedObject extends DurableObject {
  load() {
    this.ctx.storage.sql.exec("CREATE TABLE IF NOT EXISTS root (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)");
    this.ctx.storage.sql.exec("CREATE TABLE IF NOT EXISTS prepared (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)");
    this.ctx.storage.sql.exec("CREATE TABLE IF NOT EXISTS maintenance (id INTEGER PRIMARY KEY CHECK(id=1))");
    const rows = [...this.ctx.storage.sql.exec("SELECT value FROM root WHERE id=1")];
    return rows.length ? JSON.parse(rows[0].value) : null;
  }

  save(value) {
    this.ctx.storage.transactionSync(() => {
      this.ctx.storage.sql.exec("INSERT INTO root(id,value) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value", JSON.stringify(value));
      this.ctx.storage.sql.exec("DELETE FROM prepared WHERE id=1");
    });
  }

  prepare(value) {
    this.ctx.storage.sql.exec("INSERT INTO prepared(id,value) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value", JSON.stringify(value));
  }

  async fetch(request) {
    let command;
    try {
      command = await authenticate(request, this.env);
      const result = await this.ctx.blockConcurrencyWhile(async () => {
        try { return await this.execute(command); }
        catch (error) { return { failure: error instanceof Closed ? error.code : "authority_unavailable" }; }
      });
      if (result.failure) throw new Closed(result.failure);
      return response(await sign(this.env, { v: 1, scope: this.env.SCOPE, nonce: command.nonce, served_at: Date.now(), account: this.env.ACCOUNT_ID, ok: true, ...result }));
    } catch (error) {
      // Never log request bytes, keys, upstream response text or identifiers.
      const code = error instanceof Closed ? error.code : "authority_unavailable";
      if (!command) return response({ error: code }, 403);
      return response(await sign(this.env, { v: 1, scope: this.env.SCOPE, nonce: command.nonce, served_at: Date.now(), account: this.env.ACCOUNT_ID, ok: false, error: code }), 409);
    }
  }
}

export class Witness extends SignedObject {
  async execute(command) {
    const prior = this.load();
    const { action, args, role, expected } = command;
    if (action === "enroll") {
      requireThat(role === "operator" && !prior, "witness_already_enrolled_or_forbidden");
      requireThat(expected === 0 && validHash(args.digest) && typeof args.authority_account === "string" && args.snapshot?.revision === 0 && args.snapshot.scope === this.env.SCOPE && await digest(args.snapshot) === args.digest, "witness_enrollment_invalid");
      const next = { revision: 0, digest: args.digest, authority_account: args.authority_account, snapshot: args.snapshot };
      this.save(next);
      return { head: next };
    }
    requireThat(prior && role === "authority", "witness_not_enrolled_or_forbidden");
    requireThat(args.authority_account === prior.authority_account, "authority_account_mismatch");
    if (action === "head") return { head: prior };
    requireThat(expected === prior.revision && args.prior_digest === prior.digest, "witness_rollback_or_conflict");
    if (action === "verify") return { head: prior };
    requireThat(action === "advance" && validHash(args.digest), "witness_command_invalid");
    requireThat(args.snapshot?.revision === prior.revision + 1 && args.snapshot.scope === this.env.SCOPE && await digest(args.snapshot) === args.digest, "witness_snapshot_invalid");
    requireThat(args.snapshot.epoch >= prior.snapshot.epoch && prior.snapshot.revoked.every((p) => args.snapshot.revoked.includes(p)), "witness_state_regression");
    for (const [identity, intent] of Object.entries(prior.snapshot.intents)) {
      const nextIntent = args.snapshot.intents[identity];
      requireThat(nextIntent && nextIntent.key === intent.key && nextIntent.digest === intent.digest && nextIntent.participant === intent.participant && (!intent.token || nextIntent.token === intent.token) && (intent.outcome === "registered" || nextIntent.outcome !== "registered") && (intent.outcome !== "accepted" || (nextIntent.outcome === "accepted" && nextIntent.acceptance === intent.acceptance)), "witness_inventory_regression");
    }
    const next = { ...prior, revision: prior.revision + 1, digest: args.digest, snapshot: args.snapshot };
    this.save(next);
    return { head: next };
  }
}

function initialState(env) {
  return { revision: 0, epoch: 0, boot: null, head: null, sequence: 0, paused: true, killed: true, revoked: [], intents: {}, grant: null, scope: env.SCOPE };
}

export class Authority extends SignedObject {
  async witness(action, state, next = null) {
    requireThat(/^[a-f0-9]{32}$/.test(this.env.WITNESS_ACCOUNT_ID || "") && this.env.WITNESS_ACCOUNT_ID !== this.env.ACCOUNT_ID, "administration_not_independent");
    const nonce = crypto.randomUUID().replaceAll("-", "");
    requireThat(this.env.WITNESS_URL && /^[a-f0-9]{64}$/.test(this.env.WITNESS_PUBLIC_KEY || ""), "independent_witness_missing");
    const url = new URL(this.env.WITNESS_URL);
    requireThat(url.protocol === "https:" && !url.username && !url.password && url.pathname === "/command" && !url.search && !url.hash, "witness_url_invalid");
    const wire = canonical({ v: 1, scope: this.env.SCOPE, nonce, time: Date.now(), action, expected: state.revision,
      args: { authority_account: this.env.ACCOUNT_ID, prior_digest: await digest(state), ...(next ? { digest: await digest(next), snapshot: next } : {}) } });
    const request = new Request(url, { method: "POST", body: wire, headers: { "content-type": "application/json", "x-livia-role": "authority", "x-livia-signature": await hmac(this.env.WITNESS_KEY, wire) }, redirect: "manual", signal: AbortSignal.timeout(4000) });
    const reply = this.env.WITNESS_TRANSPORT ? await this.env.WITNESS_TRANSPORT.fetch(request) : await fetch(request);
    requireThat(reply.status === 200 && Number(reply.headers.get("content-length") || 0) <= 16384, "witness_unavailable");
    const body = await reply.text(); requireThat(body.length <= 16384, "witness_response_invalid");
    const result = await verifySigned(JSON.parse(body), this.env.WITNESS_PUBLIC_KEY);
    requireThat(result.ok && result.scope === this.env.SCOPE && result.nonce === nonce && Math.abs(Date.now() - result.served_at) <= 15000, "witness_response_invalid");
    requireThat(result.account === this.env.WITNESS_ACCOUNT_ID && result.account !== this.env.ACCOUNT_ID, "administration_not_independent");
    if (action !== "head") requireThat(result.head.revision === (next || state).revision && result.head.digest === await digest(next || state), "witness_rollback_or_conflict");
    requireThat(result.head.snapshot && result.head.digest === await digest(result.head.snapshot), "witness_snapshot_invalid");
    return result.head;
  }

  async execute(command) {
    const state = this.load() || initialState(this.env);
    const { action, args, role, expected } = command;
    if (action === "inspect") {
      requireThat(role === "operator", "operator_required");
      return { state, digest: await digest(state), operational_egress: false };
    }
    if (action === "recovery_status" || action === "repair") {
      requireThat(role === "operator", "operator_required");
      const external = await this.witness("head", state);
      requireThat(external.revision >= state.revision, "witness_rollback_or_conflict");
      if (action === "recovery_status") return { state, digest: await digest(state), witness_revision: external.revision, witness_digest: external.digest };
      requireThat(args.witness_revision === external.revision && args.witness_digest === external.digest, "recovery_witness_changed");
      // The independently retained complete snapshot is authoritative. Never let
      // operator-provided data invent inventory or erase consumed identities.
      this.ctx.storage.sql.exec("INSERT OR IGNORE INTO maintenance(id) VALUES(1)");
      this.save(external.snapshot);
      const repaired = clone(external.snapshot);
      repaired.revision++; repaired.epoch++; repaired.boot = null;
      repaired.paused = true; repaired.killed = true; repaired.grant = null;
      requireThat(Array.isArray(args.revocations || []) && (args.revocations || []).every((p) => validHash(p) && JSON.parse(this.env.PARTICIPANTS || "[]").includes(p)), "recovery_revocations_invalid");
      repaired.revoked = [...new Set([...repaired.revoked, ...(args.revocations || [])])];
      repaired.last_repair_revision = repaired.revision;
      this.prepare(repaired);
      await this.witness("advance", external.snapshot, repaired);
      this.save(repaired);
      this.ctx.storage.sql.exec("DELETE FROM maintenance WHERE id=1");
      return { state: repaired, digest: await digest(repaired) };
    }
    requireThat(![...this.ctx.storage.sql.exec("SELECT id FROM prepared LIMIT 1")].length && ![...this.ctx.storage.sql.exec("SELECT id FROM maintenance LIMIT 1")].length, "prepared_commit_requires_repair");
    await this.witness("verify", state);
    if (action === "read") return { state, digest: await digest(state) };
    requireThat(expected === state.revision, "authority_revision_conflict");
    const next = clone(state);
    if (action === "initialize") {
      requireThat(role === "operator" && state.head === null && validHash(args.head) && Number.isSafeInteger(args.sequence) && args.sequence >= 1, "initialization_forbidden");
      next.head = args.head; next.sequence = args.sequence;
    } else if (action === "boot") {
      requireThat(role === "runtime" && validNonce(args.boot) && args.head === state.head && args.sequence === state.sequence, "local_restore_or_boot_invalid");
      next.epoch++; next.boot = args.boot; next.paused = true; next.killed = true; next.grant = null;
    } else if (action === "advance") {
      this.requireBoot(state, command);
      requireThat(args.prior === state.head && validHash(args.head) && args.sequence === state.sequence + 1, "local_restore_or_anchor_conflict");
      next.head = args.head; next.sequence = args.sequence;
      if (["pause", "boot"].includes(args.kind)) { next.paused = true; next.grant = null; }
      if (args.kind === "revoke") {
        requireThat(validHash(args.participant) && JSON.parse(this.env.PARTICIPANTS || "[]").includes(args.participant), "revocation_invalid");
        if (!next.revoked.includes(args.participant)) next.revoked.push(args.participant);
        next.grant = null;
      }
      // Local resume never grants external authority or clears consent revocation.
    } else if (action === "release") {
      requireThat(role === "operator" && validNonce(args.boot) && state.epoch > 0 && args.boot === state.boot && args.epoch === state.epoch && args.head === state.head, "release_scope_invalid");
      requireThat(validHash(args.intent) && validHash(args.participant) && Number.isSafeInteger(args.expires_at) && args.expires_at > Date.now() && args.expires_at <= Date.now() + 3600000, "release_invalid");
      requireThat(JSON.parse(this.env.PARTICIPANTS || "[]").includes(args.participant) && !state.revoked.includes(args.participant), "participant_not_authorized");
      requireThat(!Object.values(state.intents).some((i) => i.outcome === "unknown"), "unresolved_submission");
      requireThat(!state.intents[args.intent] || state.intents[args.intent].outcome === "registered", "intent_already_consumed");
      next.paused = false; next.killed = false;
      next.grant = { intent: args.intent, participant: args.participant, expires_at: args.expires_at };
    } else if (action === "kill") {
      requireThat(role === "operator", "operator_required");
      next.killed = true; next.paused = true; next.grant = null;
    } else if (action === "register") {
      this.requireBoot(state, command); this.requirePermit(state, args);
      requireThat(validHash(args.digest) && validNonce(args.key), "intent_invalid");
      const prior = state.intents[args.intent];
      requireThat(!Object.entries(state.intents).some(([identity, value]) => identity !== args.intent && value.key === args.key), "submission_key_collision");
      requireThat(!prior || (prior.key === args.key && prior.digest === args.digest && prior.participant === args.participant), "intent_identity_conflict");
      requireThat(!prior || prior.outcome === "registered", "intent_already_consumed");
      requireThat(Object.keys(state.intents).length < 20 || prior, "submission_budget_exhausted");
      next.intents[args.intent] = prior || { key: args.key, digest: args.digest, participant: args.participant, outcome: "registered", token: null, acceptance: null };
    } else if (action === "consume") {
      this.requireBoot(state, command); this.requirePermit(state, args);
      const intent = state.intents[args.intent];
      requireThat(intent && intent.key === args.key && intent.digest === args.digest && intent.participant === args.participant && intent.outcome === "registered", "intent_already_consumed_or_conflict");
      requireThat(validNonce(args.token), "submission_token_invalid");
      next.intents[args.intent].outcome = "unknown";
      next.intents[args.intent].token = args.token;
      next.intents[args.intent].boot = state.boot;
      next.intents[args.intent].epoch = state.epoch;
      next.intents[args.intent].expires_at = state.grant.expires_at;
      next.grant = null;
    } else if (action === "check_submission") {
      this.requireBoot(state, command);
      const intent = state.intents[args.intent];
      requireThat(!state.paused && !state.killed && !state.revoked.includes(args.participant) && intent && intent.outcome === "unknown" && intent.boot === state.boot && intent.epoch === state.epoch && intent.expires_at > Date.now() && intent.token === args.token && intent.digest === args.digest && intent.participant === args.participant && args.head === state.head, "submission_not_current");
      return { state, digest: await digest(state), valid_for_ms: intent.expires_at - Date.now() };
    } else if (action === "outcome") {
      this.requireBoot(state, command);
      const intent = state.intents[args.intent];
      requireThat(intent && intent.boot === state.boot && intent.epoch === state.epoch && intent.token === args.token && intent.digest === args.digest, "outcome_identity_invalid");
      requireThat(args.outcome === "accepted" && validHash(args.acceptance), "outcome_unproven");
      requireThat(!Object.entries(state.intents).some(([identity, value]) => identity !== args.intent && value.acceptance === args.acceptance), "acceptance_identity_collision");
      requireThat(intent.outcome === "unknown" || (intent.outcome === "accepted" && intent.acceptance === args.acceptance), "outcome_conflict");
      next.intents[args.intent].outcome = "accepted"; next.intents[args.intent].acceptance = args.acceptance;
    } else if (action === "reconcile") {
      requireThat(role === "operator", "operator_required");
      const intent = state.intents[args.intent];
      requireThat(intent && intent.digest === args.digest && intent.token === args.token && validHash(args.evidence), "reconciliation_evidence_invalid");
      requireThat(args.outcome === "accepted" && validHash(args.acceptance), "reconciliation_cannot_prove_non_submission");
      requireThat(!Object.entries(state.intents).some(([identity, value]) => identity !== args.intent && value.acceptance === args.acceptance), "acceptance_identity_collision");
      requireThat(intent.outcome === "unknown" || (intent.outcome === "accepted" && intent.acceptance === args.acceptance), "outcome_conflict");
      next.intents[args.intent].outcome = "accepted"; next.intents[args.intent].acceptance = args.acceptance;
      next.intents[args.intent].evidence = args.evidence;
      // Resolution never re-arms the old intent or releases another one.
      next.paused = true; next.grant = null;
    } else throw new Closed("command_not_allowed");
    next.revision++;
    // Independent write-ahead witness precedes the authoritative commit/response.
    // Any failure between roots permanently blocks until explicit reconciliation.
    this.prepare(next);
    await this.witness("advance", state, next);
    this.save(next);
    return { state: next, digest: await digest(next) };
  }

  requireBoot(state, command) {
    requireThat(command.role === "runtime" && command.args.boot === state.boot && command.args.epoch === state.epoch, "boot_fence_invalid");
  }

  requirePermit(state, args) {
    requireThat(!state.paused && !state.killed && state.head === args.head, "egress_paused_or_snapshot_stale");
    requireThat(state.grant && state.grant.intent === args.intent && state.grant.participant === args.participant && state.grant.expires_at > Date.now(), "release_missing_or_expired");
    requireThat(JSON.parse(this.env.PARTICIPANTS || "[]").includes(args.participant) && !state.revoked.includes(args.participant), "participant_not_authorized");
  }
}

export default {
  async fetch(request, env) {
    if (request.method === "GET" && new URL(request.url).pathname === "/health") return response({ process: "ok", role: env.ROLE, operational_egress: false });
    if (!validHash(env.SCOPE) || !["authority", "witness"].includes(env.ROLE)) return response({ error: "deployment_not_configured" }, 503);
    // Reject unauthenticated Internet traffic before dispatching to billed DOs.
    // The Object authenticates again, including direct service-binding calls.
    try { await authenticate(request.clone(), env); }
    catch (error) { return response({ error: error instanceof Closed ? error.code : "authentication_failed" }, 403); }
    const namespace = env.ROLE === "authority" ? env.AUTHORITY : env.WITNESS;
    return namespace.get(namespace.idFromName(env.SCOPE)).fetch(request);
  },
};
