"""B2 adversarial fixtures; these never demonstrate real WhatsApp or OpenAI."""

from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient
from test_waha_b1 import (
    CHANNEL,
    CHAT,
    KEY,
    PARTICIPANT,
    FixtureGenerator,
    envelope,
    request,
    settings,
)

from rj_studio_ai.providers.waha import WahaAPI, WahaIdentityError
from rj_studio_ai.waha_cli import operator_request
from rj_studio_ai.waha_live import create_waha_app


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (httpx.ReadTimeout, "waha_contact_timeout"),
        (httpx.ConnectTimeout, "waha_contact_timeout"),
        (httpx.ConnectError, "waha_contact_transport_failed"),
        (httpx.RemoteProtocolError, "waha_contact_transport_failed"),
    ],
)
def test_contact_read_failure_is_sanitized_and_never_retried(failure, code):
    calls = []

    def handler(req):
        calls.append(req)
        raise failure("PRIVATE_PROVIDER_DETAIL", request=req)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        api = WahaAPI(base_url="http://127.0.0.1:3000", api_key=KEY, client=client)
        with pytest.raises(WahaIdentityError, match="^" + code + "$"):
            api.identities_for(PARTICIPANT)
    assert len(calls) == 1


@pytest.mark.parametrize("status", [301, 401, 404, 422, 429, 500])
def test_contact_unexpected_http_is_not_identity_authority(status):
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(status, text="PRIVATE"))
    ) as client:
        api = WahaAPI(base_url="http://127.0.0.1:3000", api_key=KEY, client=client)
        with pytest.raises(WahaIdentityError, match="^waha_contact_http_unexpected$"):
            api.identities_for(PARTICIPANT)


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {},
        {"numberExists": False},
        {"numberExists": 1, "chatId": CHAT},
        {"numberExists": True, "chatId": "123@g.us"},
        {"numberExists": True, "chatId": CHAT, "pn": "invalid"},
        {"numberExists": True, "chatId": []},
    ],
)
def test_contact_invalid_identity_fails_closed(data):
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))
    ) as client:
        api = WahaAPI(base_url="http://127.0.0.1:3000", api_key=KEY, client=client)
        with pytest.raises(WahaIdentityError, match="^waha_contact_identity_unverified$"):
            api.identities_for(PARTICIPANT)


def prepare_app(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "rj_studio_ai.waha_live.generator_from_settings",
        lambda _: FixtureGenerator(Event(), Event()),
    )
    monkeypatch.setattr(
        WahaAPI, "session_info", lambda _: {"status": "WORKING", "me": {"id": CHANNEL}}
    )
    monkeypatch.setattr(
        WahaAPI,
        "identities_for",
        lambda _, phone: {phone[1:] + "@c.us", "111@lid" if phone == PARTICIPANT else "222@lid"},
    )
    return create_waha_app(settings(tmp_path))


def test_resume_binds_explicit_lids_and_reconnect_requires_revalidation(tmp_path, monkeypatch):
    app = prepare_app(tmp_path, monkeypatch)
    auth = {"Authorization": "Bearer " + KEY}
    with TestClient(app) as client:
        response = client.post("/ops/resume", headers=auth)
        assert response.json() == {"paused": False, "egress": False, "scope": "inference_only"}
        req = request(envelope() | {"event": "session.status", "payload": {"status": "STOPPED"}})
        assert (
            client.post("/webhooks/waha", content=req.body, headers=req.headers).status_code == 204
        )
        assert app.state.journal.paused
        req = request(envelope() | {"event": "session.status", "payload": {"status": "WORKING"}})
        assert (
            client.post("/webhooks/waha", content=req.body, headers=req.headers).status_code == 204
        )
        assert app.state.journal.paused
        assert client.post("/ops/resume", headers=auth).json()["paused"] is False
        assert not app.state.store.authorize_waha_http(None)


def test_verified_lid_ingress_is_canonical_and_duplicate_revocation_stays_durable(
    tmp_path, monkeypatch
):
    app = prepare_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        assert (
            client.post("/ops/resume", headers={"Authorization": "Bearer " + KEY}).status_code
            == 200
        )
        raw = envelope("pare")
        raw["me"] = {"id": "222@lid"}
        raw["payload"].update({"from": "111@lid", "to": "222@lid", "id": "false_111@lid_ONE"})
        req = request(raw)
        for _ in range(2):
            assert (
                client.post("/webhooks/waha", content=req.body, headers=req.headers).status_code
                == 204
            )
        assert len(app.state.store.get_history(provider="waha", customer_address=CHAT)) == 1
        assert not app.state.journal.permits_generation(CHAT)
        assert (
            client.post("/ops/resume", headers={"Authorization": "Bearer " + KEY}).status_code
            == 200
        )
        assert not app.state.journal.permits_generation(CHAT)
        assert not app.state.store.authorize_waha_http(None)


@pytest.mark.parametrize(
    "scenario", ["timeout", "collision", "rebind", "disconnect", "not_working"]
)
def test_failed_resume_revokes_previous_running_state(tmp_path, monkeypatch, scenario):
    app = prepare_app(tmp_path, monkeypatch)
    auth = {"Authorization": "Bearer " + KEY}
    with TestClient(app) as client:
        assert client.post("/ops/resume", headers=auth).status_code == 200
        assert not app.state.journal.paused
        calls = []

        def contacts(_, phone):
            calls.append(phone)
            if scenario == "timeout":
                raise WahaIdentityError("waha_contact_timeout")
            if scenario == "collision":
                return {"111@lid", phone[1:] + "@c.us"}
            return {phone[1:] + "@c.us"}

        sessions = iter(
            [
                {
                    "status": "STOPPED" if scenario == "not_working" else "WORKING",
                    "me": {"id": CHANNEL},
                },
                {
                    "status": "STOPPED" if scenario == "disconnect" else "WORKING",
                    "me": {"id": CHAT if scenario == "rebind" else CHANNEL},
                },
            ]
        )
        monkeypatch.setattr(WahaAPI, "identities_for", contacts)
        monkeypatch.setattr(WahaAPI, "session_info", lambda _: next(sessions))
        result = client.post("/ops/resume", headers=auth)
        assert result.status_code == 409
        assert app.state.journal.paused
        assert not app.state.journal.permits_generation(CHAT)
        assert not app.state.store.authorize_waha_http(None)
        if scenario == "not_working":
            assert not calls


@pytest.mark.parametrize("action", ["pause", "revoke"])
def test_operator_or_consent_change_during_contacts_cannot_be_overwritten(
    tmp_path, monkeypatch, action
):
    app = prepare_app(tmp_path, monkeypatch)

    def contacts(_, phone):
        app.state.journal.change(action, CHAT if action == "revoke" else None)
        return {phone[1:] + "@c.us"}

    monkeypatch.setattr(WahaAPI, "identities_for", contacts)
    with TestClient(app) as client:
        result = client.post("/ops/resume", headers={"Authorization": "Bearer " + KEY})
        assert result.status_code == 409
        assert result.json()["detail"] == "waha_controls_changed_during_verification"
        assert app.state.journal.paused
        assert not app.state.journal.permits_generation(CHAT)


@pytest.mark.parametrize(("action", "expected"), [("resume", 75), ("pause", 10), ("ready", 10)])
def test_operator_client_budget_covers_contact_validation(monkeypatch, action, expected):
    def handler(req):
        assert req.extensions["timeout"]["read"] == expected
        return httpx.Response(200, json={"fixture": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr("rj_studio_ai.waha_cli.httpx.Client", lambda **_: client)
    assert operator_request({"WAHA_OPERATOR_TOKEN": KEY}, action) == {"fixture": True}
