import assert from "node:assert/strict";
import { createHmac, createHash, generateKeyPairSync, randomBytes, verify } from "node:crypto";
import { fileURLToPath } from "node:url";
import { Miniflare, convertV4MiniflareOptions } from "miniflare";

const scope = process.env.LIVIA_FIXTURE_SCOPE || "a".repeat(64), head = "b".repeat(64), intent = "c".repeat(64), participant = process.env.LIVIA_FIXTURE_PARTICIPANT || "d".repeat(64);
const account = "1".repeat(32), witnessAccount = "2".repeat(32);
const key = randomBytes(32).toString("hex"), operator = randomBytes(32).toString("hex"), witnessKey = randomBytes(32).toString("hex");
const stable = (v) => v === null || typeof v !== "object" ? JSON.stringify(v) : Array.isArray(v) ? `[${v.map(stable).join(",")}]` : `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}:${stable(v[k])}`).join(",")}}`;
const nonce = () => randomBytes(16).toString("hex");
const hash = (v) => createHash("sha256").update(stable(v)).digest("hex");

function signing() {
  const pair = generateKeyPairSync("ed25519");
  const jwk = pair.privateKey.export({ format: "jwk" });
  return { private: JSON.stringify(jwk), public: Buffer.from(jwk.x, "base64url").toString("hex"), key: pair.publicKey };
}

async function fixture(t, { sameAccount = false, witnessFailure = false } = {}) {
  const authoritySigning = signing(), witnessSigning = signing();
  const common = { modules: true, scriptPath: fileURLToPath(new URL("../src/worker.mjs", import.meta.url)), compatibilityDate: "2026-11-20" };
  const options = convertV4MiniflareOptions({ workers: [
    { ...common, name: "authority", bindings: { ROLE: "authority", SCOPE: scope, ACCOUNT_ID: account, WITNESS_ACCOUNT_ID: sameAccount ? account : witnessAccount, RUNTIME_KEY: key, OPERATOR_KEY: operator, SIGNING_JWK: authoritySigning.private, WITNESS_KEY: witnessKey, WITNESS_URL: "https://witness.example.workers.dev/command", WITNESS_PUBLIC_KEY: witnessSigning.public, PARTICIPANTS: JSON.stringify([participant]) }, serviceBindings: { WITNESS_TRANSPORT: witnessFailure ? async () => new Response("", { status: 503 }) : "witness" }, durableObjects: { AUTHORITY: { className: "Authority", useSQLite: true } } },
    { ...common, name: "witness", bindings: { ROLE: "witness", SCOPE: scope, ACCOUNT_ID: sameAccount ? account : witnessAccount, OPERATOR_KEY: operator, AUTHORITY_KEY: witnessKey, SIGNING_JWK: witnessSigning.private }, durableObjects: { WITNESS: { className: "Witness", useSQLite: true } } },
  ] });
  const mf = new Miniflare({ ...options, unsafeInspectDurableObjects: true });
  t.after(() => mf.dispose());
  async function command(worker, action, args = {}, { role = "runtime", expected, time = Date.now(), secret, signature, requestScope = scope } = {}) {
    const requestNonce = nonce();
    const payload = { v: 1, scope: requestScope, nonce: requestNonce, time, action, args, ...(expected === undefined ? {} : { expected }) };
    const body = stable(payload);
    const selectedKey = secret || (role === "operator" ? operator : role === "authority" ? witnessKey : key);
    const fetcher = await mf.getWorker(worker);
    const response = await fetcher.fetch("https://unit.test/command", { method: "POST", body, redirect: "manual", headers: { "content-type": "application/json", "x-livia-role": role, "x-livia-signature": signature || createHmac("sha256", selectedKey).update(body).digest("hex") } });
    const raw = await response.json();
    if (raw.payload) {
      assert(verify(null, Buffer.from(stable(raw.payload)), worker === "authority" ? authoritySigning.key : witnessSigning.key, Buffer.from(raw.signature, "hex")));
      assert.equal(raw.payload.nonce, requestNonce);
    }
    return { status: response.status, ...raw.payload, error: raw.payload?.error || raw.error };
  }
  const inspected = await command("authority", "inspect", {}, { role: "operator" });
  const enrolled = await command("witness", "enroll", { authority_account: account, digest: inspected.digest }, { role: "operator", expected: 0 });
  assert(enrolled.ok);
  async function mutate(action, args = {}, role = "runtime") {
    const current = await command("authority", "read");
    if (!current.ok) return current;
    return command("authority", action, args, { role, expected: current.state.revision });
  }
  async function initialize() {
    const result = await mutate("initialize", { head, sequence: 1 }, "operator");
    if (!result.ok) return result;
    return mutate("boot", { head, sequence: 1, boot: "e".repeat(32) });
  }
  async function release() {
    const current = await command("authority", "read");
    const s = current.state;
    return mutate("release", { boot: s.boot, epoch: s.epoch, head: s.head, participant, intent, expires_at: Date.now() + 60000 }, "operator");
  }
  async function runtime(action, args = {}) {
    const current = await command("authority", "read");
    const s = current.state;
    return mutate(action, { boot: s.boot, epoch: s.epoch, head: s.head, intent, participant, digest: "f".repeat(64), key: "9".repeat(32), ...args });
  }
  async function snapshot(worker = "authority", className = "Authority") {
    const storage = await mf.unsafeGetDurableObjectStorage(worker, className, { name: scope });
    return { storage, rows: await storage.exec("SELECT value FROM root WHERE id=1") };
  }
  return { mf, command, mutate, initialize, release, runtime, snapshot, clientConfig: { url: "https://authority.example.workers.dev/command", scope, account, witness_account: witnessAccount, public_key: authoritySigning.public, runtime_key: key }, operatorKey: operator };
}


export { fixture, scope, head, intent, participant, account, key, operator, nonce, hash };
