// Exercise the actual patched library's login and legacy event registration.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const source = fs.readFileSync('/app/node_modules/whatsapp-web.js/src/Client.js', 'utf8');
const begin = "            await this.pupPage.evaluate(() => {\n                const Cmd =";
const end = "                if (Socket.hasSynced === true) {\n                    window.onAppStateHasSyncedEvent();\n                }\n            });";
const start = source.indexOf(begin);
const finish = source.indexOf(end, start);
assert.ok(start > 0 && finish > start, 'event registration callback exists');
const callback = source.slice(start + '            await this.pupPage.evaluate('.length,
  finish + end.length - ');'.length);
for (const route of ['/login/', '/']) {
  const bus = new EventEmitter();
  const socket = new EventEmitter();
  const cmd = new EventEmitter();
  const window = {
    location: {pathname: route},
    require(name) {
      if (name === 'WAWebBackendEventBus') return {BackendEventBus: bus};
      if (name === 'WAWebSocketModel') {
        assert.equal(route, '/', 'login does not load unavailable Socket module');
        return {Socket: socket};
      }
      if (name === 'WAWebCmd') return {Cmd: cmd};
      throw new Error('unexpected module');
    },
    onAuthAppStateChangedEvent: value => states.push(value),
    onAppStateHasSyncedEvent: () => {synced++;},
  };
  let synced = 0;
  const states = [];
  const register = () => vm.runInNewContext('(' + callback + ')()', {window});
  register(); register();
  if (route === '/login/') {
    bus.emit('set_socket_state', 'UNPAIRED');
    bus.emit('open_socket_stream');
  } else {
    socket.emit('change:state', socket, 'UNPAIRED');
    socket.emit('change:hasSynced', socket, undefined);
    socket.emit('change:hasSynced', socket, false);
    assert.equal(synced, 0, 'logout teardown must not emit authenticated readiness');
    socket.emit('change:hasSynced', socket, true);
  }
  assert.deepEqual(states, ['UNPAIRED'], 're-injection does not duplicate listeners');
  assert.equal(synced, 1, 'one real sync event produces one readiness callback');
}
console.log('WEBJS login/legacy event registration and logout guard passed');
