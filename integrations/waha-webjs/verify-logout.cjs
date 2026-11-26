// Run the patched navigation callback itself; no browser, credentials, or network.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('/app/node_modules/whatsapp-web.js/src/Client.js', 'utf8');
const match = source.match(/this\.pupPage\.on\('framenavigated', (async \(frame\) => \{[\s\S]*?\n        \})\);/);
assert.ok(match, 'navigation callback exists');
const makeNavigate = vm.runInNewContext('(function(){return ' + match[1] + ';})');

(async () => {
  for (const [url, flagged] of [['https://web.whatsapp.com/?post_logout=1', false],
    ['https://web.whatsapp.com/', true]]) {
    const events = [];
    const client = {
      lastLoggedOut: flagged,
      emit: (...args) => events.push(args),
      authStrategy: {logout: async () => {throw new Error('must preserve profile');}},
      pupPage: {evaluate: async () => {throw new Error('must stay stopped');}},
      inject: async () => {throw new Error('must not automatically recover after logout');},
    };
    // The runtime event name is injected into the same lexical scope as Client.js.
    const factory = vm.runInNewContext('(function(){return ' + match[1] + ';})', {Events:{DISCONNECTED:'disconnected'}});
    await factory.call(client)({parentFrame:()=>null, url:()=>url});
    assert.deepEqual(events, [['disconnected','LOGOUT']], 'logout still stops the channel');
    assert.equal(client.lastLoggedOut, false);
  }
  let injections = 0;
  const connected = {lastLoggedOut:false, pupPage:{evaluate:async()=>true},
    inject:async()=>{injections++;},emit:()=>{throw new Error('unexpected disconnect');}};
  await makeNavigate.call(connected)({parentFrame:()=>null,url:()=>'https://web.whatsapp.com/'});
  assert.equal(injections, 0, 'existing bridge is retained on normal navigation');
  connected.pupPage.evaluate = async()=>false;
  await makeNavigate.call(connected)({parentFrame:()=>null,url:()=>'https://web.whatsapp.com/'});
  assert.equal(injections, 1, 'normal navigation can re-inject a missing bridge');
  const begin = source.indexOf('    async logout() {');
  const finish = source.indexOf('\n    }\n', begin) + '\n    }'.length;
  assert.ok(begin > 0 && finish > begin);
  const logout = vm.runInNewContext('({' + source.slice(begin,finish) + '}).logout');
  let deleted = 0;
  await logout.call({pupPage:{evaluate:async()=>{}},
    pupBrowser:{close:async()=>{},isConnected:()=>false},
    authStrategy:{logout:async()=>{deleted++;}}});
  assert.equal(deleted, 1, 'explicit operator logout retains credential cleanup');
  console.log('Navigation logout stops channel without profile deletion; explicit logout still cleans up');
})().catch(error=>{console.error(error);process.exitCode=1;});
