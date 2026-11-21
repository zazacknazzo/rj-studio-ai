"""Real ASGI/TestClient + SQLite; external sockets blocked by the offline runner."""

import asyncio

import pytest
from starlette.testclient import TestClient
from test_telnyx_authentication import NOW, PHONE, PRIVATE_TEXT, signed
from test_telnyx_authentication import private_key as private_key
from test_telnyx_authentication import settings as settings
from test_telnyx_lifecycle import account
from test_telnyx_messages import wire

from rj_studio_ai.telnyx_asgi import create_telnyx_offline_app


@pytest.fixture
def app(settings, tmp_path):
    return create_telnyx_offline_app(settings, tmp_path / "http.db", wall_clock=lambda: NOW)


def post(client, key, payload=None, **kwargs):
    request = signed(key, wire() if payload is None else payload)
    return client.post(
        "/webhooks/telnyx",
        content=request.body,
        headers={"content-type": request.content_type, **request.headers},
        **kwargs,
    )


def count(app, table):
    with app.store._connect() as db:
        return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_commit_observable_at_ack_and_replay_after_lost_ack(app, private_key):
    with TestClient(app) as client:
        ack = post(client, private_key)
        assert ack.status_code == 204 and ack.content == b""
        assert "content-length" not in ack.headers
        assert count(app, "messages") == 1
        assert count(app, "inbound_event_receipts") == 1
        assert post(client, private_key).status_code == 204
        assert count(app, "messages") == 1
        assert count(app, "outbound_deliveries") == 0
        assert client.get("/health").json()["mode"] == "offline"


def test_invalid_signature_precedes_json_and_has_no_effects(app, private_key):
    request = signed(private_key, body=b"not-json")
    with TestClient(app) as client:
        headers = {"content-type": "application/json", **request.headers}
        assert (
            client.post(
                "/webhooks/telnyx", content=b"not-json-mutated", headers=headers
            ).status_code
            == 403
        )
        assert (
            client.post("/webhooks/telnyx", content=request.body, headers=headers).status_code
            == 422
        )
    assert count(app, "messages") == 0
    assert count(app, "operational_events") == 0


@pytest.mark.parametrize("kind", ["text", "echo", "edit", "revoke"])
def test_supported_events_through_http(app, private_key, kind):
    with TestClient(app) as client:
        assert post(client, private_key, wire(kind)).status_code == 204
    assert count(app, "messages") == (1 if kind == "text" else 0)
    assert count(app, "operational_events") == (0 if kind == "text" else 1)


def test_lifecycle_ingress_works_while_channel_blocked(app, private_key):
    with TestClient(app) as client:
        assert post(client, private_key, account("PARTNER_REMOVED")).status_code == 204
        assert post(client, private_key).status_code == 204
    assert count(app, "messages") == 1
    with app.store._connect() as db:
        assert db.execute("SELECT state FROM channel_lifecycle").fetchone() == ("blocked",)
        assert db.execute("SELECT state FROM message_processing").fetchone() == ("suppressed",)


def test_raw_asgi_duplicate_header_does_not_become_dict(app, private_key):
    request = signed(private_key, wire())

    async def run():
        sent = []

        async def receive():
            pytest.fail("duplicate headers must reject before reading body")

        async def send(message):
            sent.append(message)

        await app(
            {
                "type": "http",
                "method": "POST",
                "path": "/webhooks/telnyx",
                "headers": [
                    (b"content-type", b"application/json"),
                    *[(k.encode(), v.encode()) for k, v in request.headers.items()],
                    (b"Telnyx-Timestamp", str(NOW).encode()),
                ],
            },
            receive,
            send,
        )
        assert sent[0]["status"] == 400

    asyncio.run(run())
    assert count(app, "messages") == 0


def test_errors_and_metrics_do_not_expose_content_or_scope(app, private_key, caplog):
    payload = wire()
    payload["data"]["payload"]["organization_id"] = PRIVATE_TEXT
    with TestClient(app) as client:
        response = post(client, private_key, payload)
        assert response.status_code == 422
    observed = response.text + str(app.metrics.snapshot()) + caplog.text
    assert PRIVATE_TEXT not in observed and PHONE not in observed


def test_no_production_route_or_provider_enablement(settings):
    from rj_studio_ai.config import Settings
    from rj_studio_ai.main import create_app

    with pytest.raises(ValueError):
        Settings(_env_file=None, whatsapp_provider="telnyx", delivery_mode="proactive")
    production = create_app(settings)
    assert "/webhooks/telnyx" not in production.openapi()["paths"]
