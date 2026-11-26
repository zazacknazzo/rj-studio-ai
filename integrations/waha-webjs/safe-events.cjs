// Diagnostic lifecycle only: never retain QR, contacts, messages, or auth payloads.
const fs = require('node:fs');
const path = '/tmp/waha-safe-events.jsonl';
const reasons = new Set(['LOGOUT', 'Max qrcode retries reached', 'CONFLICT', 'UNPAIRED',
  'UNPAIRED_IDLE', 'CONNECTED', 'OPENING', 'PAIRING', 'TIMEOUT', 'UNLAUNCHED',
  'DEPRECATED_VERSION', 'PROXYBLOCK', 'TOS_BLOCK', 'SMB_TOS_BLOCK']);
module.exports = client => {
  for (const event of ['authenticated', 'ready', 'disconnected', 'auth_failure', 'change_state']) {
    client.on(event, reason => {
      try {
        const record = {at: new Date().toISOString(), event};
        if (event === 'disconnected' || event === 'change_state')
          record.reason = reasons.has(reason) ? reason : 'other';
        const prior = fs.existsSync(path) ? fs.readFileSync(path, 'utf8').trim().split('\n').slice(-127) : [];
        fs.writeFileSync(path, [...prior, JSON.stringify(record)].join('\n') + '\n', {mode:0o600});
      } catch { /* diagnostics cannot alter lifecycle behavior */ }
    });
  }
};
