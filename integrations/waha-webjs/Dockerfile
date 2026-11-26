FROM devlikeapro/waha:arm-2026.10.1@sha256:64ecee1e8cea097d8c4b675b4940b12e0b4836ca5923a34633272c263df090fd
COPY safe-events.cjs /opt/waha-safe-events.cjs
COPY socket-patch.json apply-patch.cjs verify-patch.cjs verify-logout.cjs /tmp/waha-socket-patch/
RUN node /tmp/waha-socket-patch/apply-patch.cjs \
    && node --check /app/node_modules/whatsapp-web.js/src/Client.js \
    && node /tmp/waha-socket-patch/verify-patch.cjs \
    && node /tmp/waha-socket-patch/verify-logout.cjs \
    && rm -r /tmp/waha-socket-patch
