// Test-only stdio bridge: Python reaches actual workerd without IP sockets.
// No network proxy or restore method is shipped in the deployed Worker.
import { createInterface } from "node:readline";
import { fixture } from "./runtime.mjs";

const cleanups = [];
const runtime = await fixture({ after: (fn) => cleanups.push(fn) });
process.stdout.write(JSON.stringify({ ready: true, config: runtime.clientConfig, operator: runtime.operatorKey }) + "\n");
const lines = createInterface({ input: process.stdin });
for await (const line of lines) {
  try {
    const message = JSON.parse(line);
    if (message.action === "close") break;
    if (message.action === "snapshot") {
      const saved = await runtime.snapshot();
      process.stdout.write(JSON.stringify({ value: saved.rows[0].value }) + "\n");
    } else if (message.action === "restore") {
      const saved = await runtime.snapshot();
      await saved.storage.exec("UPDATE root SET value=? WHERE id=1", message.value);
      process.stdout.write('{"restored":true}\n');
    } else {
      const worker = await runtime.mf.getWorker("authority");
      const response = await worker.fetch("https://unit.test/command", { method: "POST", body: message.body, headers: message.headers, redirect: "manual" });
      process.stdout.write(JSON.stringify({ status: response.status, body: await response.text() }) + "\n");
    }
  } catch (error) {
    process.stdout.write(JSON.stringify({ bridge_error: error.name }) + "\n");
  }
}
for (const close of cleanups) await close();
lines.close();
process.stdin.destroy();
