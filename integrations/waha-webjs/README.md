# WEBJS login compatibility

The pinned WAHA 2026.10.1 image waits for WAWebSocketModel during authentication.
On 26 November 2026 the new WhatsApp /login/ route did not expose that module.
The browser displayed the login page but the session stayed STARTING with no API QR.

This derived image backports the provider's [socket fix
38eb45b](https://github.com/devlikeapro/whatsapp-web.js/commit/38eb45b2759450cc6fccb6a7a3f2cbc3bdb87db2),
published 24 November. It uses BackendEventBus for the login route and keeps
the existing Socket listeners on the authenticated route. The vendor's additional
hasSynced logout guard is retained. All other vendor modifications remain intact.
No dependency download is performed during the build.

Both the original Client.js and the patched result are checked against SHA-256
values in socket-patch.json. A source change or non-unique hunk fails the build.
The build checks JavaScript syntax and exercises actual event-registration code
for both routes, re-injection, and logout teardown without any WhatsApp network call.

Build from the repository root:

```sh
docker build -t rj-livia-waha-webjs:20261126 integrations/waha-webjs
```

The private-test Compose override selects this image. The base Compose and its
original pinned image remain available. Session volumes and webhook authentication
are unchanged. Runtime validation reached SCAN_QR_CODE through the authenticated
WAHA API; pairing and real bidirectional delivery require separate evidence.
