"""Unsupported payloads never ACK; visibility has bounded, content-free storage."""

import sqlite3

import pytest
from starlette.testclient import TestClient
from test_telnyx_asgi import app as app
from test_telnyx_asgi import count, post
from test_telnyx_authentication import NOW, PHONE, PRIVATE_TEXT, signed
from test_telnyx_authentication import private_key as private_key
from test_telnyx_authentication import settings as settings
from test_telnyx_lifecycle import account
from test_telnyx_messages import wire

from rj_studio_ai.deadline import ExecutionDeadline
from rj_studio_ai.providers.base import InvalidWebhookPayload
from rj_studio_ai.telnyx_asgi import create_telnyx_offline_app
from rj_studio_ai.webhook_ingress import receive_telnyx_messages


@pytest.mark.parametrize(
    "kind",
    [
        "image",
        "audio",
        "video",
        "document",
        "future_type",
        "unknown_event",
        "future_lifecycle",
        "mixed_array",
        "waba",
    ],
)
def test_unsupported_visible_durably_without_success_or_content(app, private_key, settings, kind):
    payload = wire()
    if kind == "unknown_event":
        payload["data"]["event_type"] = PRIVATE_TEXT
    elif kind == "future_lifecycle":
        payload = account(PRIVATE_TEXT)
    elif kind == "mixed_array":
        payload = [payload, wire("image")]
    elif kind == "waba":
        payload["data"]["event_type"] = "whatsapp.messages"
    else:
        payload["data"]["payload"]["body"]["type"] = kind
    with TestClient(app) as client:
        assert post(client, private_key, payload).status_code == 422
        assert post(client, private_key, payload).status_code == 422
        assert client.get("/metrics").json()["responses"]["422"] == 2
    assert count(app, "messages") == 0
    assert count(app, "operational_events") == 0
    assert count(app, "channel_lifecycle") == 0
    with app.store._connect() as db:
        stored = db.execute("SELECT * FROM telnyx_ingress_rejections").fetchall()
        assert stored[0][:2] == ("payload_rejected", 2)
        columns = [row[1] for row in db.execute("PRAGMA table_info(telnyx_ingress_rejections)")]
        assert columns == ["reason", "observations", "first_seen_at", "last_seen_at"]
    assert PRIVATE_TEXT not in str(stored) and PHONE not in str(stored)
    restarted = create_telnyx_offline_app(
        settings, app.store._database_path, wall_clock=lambda: NOW
    )
    with restarted.store._connect() as db:
        assert db.execute("SELECT observations FROM telnyx_ingress_rejections").fetchone() == (2,)


def test_mixed_local_batch_cannot_commit_supported_sibling(app, private_key):
    with pytest.raises(InvalidWebhookPayload):
        receive_telnyx_messages(
            (signed(private_key, wire()), signed(private_key, wire("image"))),
            adapter=app.adapter,
            store=app.store,
            deadline=ExecutionDeadline.start(),
        )
    assert count(app, "messages") == 0


def test_media_echo_still_durably_pauses_without_inbound_generation(app, private_key):
    payload = wire("echo")
    payload["data"]["payload"]["body"] = {"type": "image", "image": {"caption": PRIVATE_TEXT}}
    with TestClient(app) as client:
        assert post(client, private_key, payload).status_code == 204
    assert count(app, "human_pause_effects") == 1
    assert count(app, "messages") == 0
    assert count(app, "telnyx_ingress_rejections") == 0


def test_rejection_commit_failure_returns_503_and_no_false_observation(app, private_key):
    with app.store._connect() as db:
        db.execute(
            "CREATE TRIGGER synthetic_reject BEFORE INSERT ON telnyx_ingress_rejections "
            "BEGIN SELECT RAISE(ABORT,'synthetic fail'); END"
        )
    with TestClient(app) as client:
        assert post(client, private_key, wire("image")).status_code == 503
        assert client.get("/metrics").json()["responses"]["503"] == 1
    assert count(app, "telnyx_ingress_rejections") == 0


def test_health_and_six_readiness_dimensions_never_grant_egress(app, private_key):
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        ready = client.get("/ready")
        assert ready.status_code == 200
        assert ready.json() == {
            "mode": "offline",
            "ingress": True,
            "persistence": True,
            "administration": False,
            "generation": False,
            "egress": False,
            "operational_channel": False,
            "quarantined": True,
        }
        assert post(client, private_key, account()).status_code == 204
        assert client.get("/ready").json() == ready.json()
        with app.store._connect() as lock:
            lock.execute("BEGIN IMMEDIATE")
            degraded = client.get("/ready")
            assert degraded.status_code == 503
            assert degraded.json()["ingress"] is True
            assert degraded.json()["persistence"] is False
            assert client.get("/health").status_code == 200


def test_missing_observation_schema_fails_readiness(app):
    with app.store._connect() as db:
        db.execute("DROP TABLE telnyx_ingress_rejections")
    assert app.readiness()["persistence"] is False


def test_counter_labels_cannot_become_an_identifier_archive(app):
    with app.store._connect() as db, pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO telnyx_ingress_rejections VALUES(?,1,'t','t')", (PRIVATE_TEXT,))
