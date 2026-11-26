// Backport the upstream login-route socket fix without replacing vendor guards.
const fs = require('node:fs');
const crypto = require('node:crypto');
const patch = require('./socket-patch.json');
const target = '/app/node_modules/whatsapp-web.js/src/Client.js';
const digest = text => crypto.createHash('sha256').update(text).digest('hex');
let source = fs.readFileSync(target, 'utf8');
if (digest(source) !== patch.source_sha256) throw new Error('Unexpected WEBJS source');
for (const {before, after} of patch.hunks) {
  if (source.split(before).length !== 2) throw new Error('Non-unique WEBJS patch hunk');
  source = source.replace(before, after);
}
if (digest(source) !== patch.result_sha256) throw new Error('Unexpected WEBJS patch result');
fs.writeFileSync(target, source);
