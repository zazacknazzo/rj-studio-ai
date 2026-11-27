"""Read-only account observations cannot become false connection/send readiness."""

import json

import pytest
import requests

from rj_studio_ai.telnyx_preflight import (
    PreflightSettings,
    TelnyxAccountProbe,
    diagnose,
    main,
)

PHONE = "+12025550123"
KEY = "private-test-key-never-rendered"


def settings(**values):
    return PreflightSettings(
        _env_file=None,
        telnyx_api_key=KEY,
        telnyx_phone_number=PHONE,
        telnyx_waba_id="12345",
        **values,
    )


def response(body, status=200, content_type="application/json"):
    result = requests.Response()
    result.status_code = status
    result.headers["Content-Type"] = content_type
    result._content = body if isinstance(body, bytes) else json.dumps(body).encode()
    result._content_consumed = True
    return result


def install(monkeypatch, responses):
    calls = []

    class Session:
        trust_env = True

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def get(self, url, **kwargs):
            calls.append((url, kwargs, self.trust_env))
            outcome = responses[len(calls) - 1]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(requests, "Session", Session)
    return calls


def page(data, **meta):
    return {"data": data, "meta": {"total_pages": 1, **meta}}


def test_default_configuration_only_never_opens_a_session(monkeypatch, capsys):
    install(monkeypatch, [])
    monkeypatch.setenv("TELNYX_API_KEY", KEY)
    assert main(["--env-file", "/not-present"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "configuration_only"
    assert report["configuration"]["api_key"] is True
    assert report["checks"] == {}
    assert KEY not in json.dumps(report)


@pytest.mark.parametrize(
    "key,state", [("", "credential_missing"), ("bad\nkey", "credential_invalid")]
)
def test_missing_or_invalid_credential_never_attempts_network(monkeypatch, key, state):
    calls = install(monkeypatch, [])
    report = diagnose(PreflightSettings(_env_file=None, telnyx_api_key=key), live=True)
    assert not calls
    assert {check["state"] for check in report["checks"].values()} == {state}
    assert report["egress_authorized"] is False


@pytest.mark.parametrize(
    "status,state",
    [
        (401, "authentication_denied"),
        (403, "permission_denied"),
        (404, "resource_unavailable"),
        (429, "rate_limited"),
        (302, "http_unavailable"),
        (503, "http_unavailable"),
    ],
)
def test_denial_is_not_reported_as_no_accounts_or_healthy(monkeypatch, caplog, status, state):
    remote = {"errors": [{"detail": KEY + PHONE}]}
    calls = install(monkeypatch, [response(remote, status), response(remote, status)])
    report = diagnose(settings(), live=True)
    for check in report["checks"].values():
        assert check == {"state": state, "observed_count": None}
    assert report["egress_authorized"] is False
    rendered = json.dumps(report) + caplog.text
    assert KEY not in rendered and PHONE not in rendered
    assert len(calls) == 2  # no automatic retry or redirect
    for url, policy, trust_env in calls:
        assert url.startswith("https://api.telnyx.com/v2/whatsapp/")
        assert policy == {
            "headers": {"Authorization": "Bearer " + KEY},
            "timeout": (5, 10),
            "allow_redirects": False,
            "stream": True,
        }
        assert trust_env is False


def test_realistic_phone_schema_compares_waba_without_inventing_profile_evidence(monkeypatch):
    accounts = [{"record_type": "whatsapp_business_account", "waba_id": "12345"}]
    phones = [
        {
            "record_type": "whatsapp_business_phone_number",
            "phone_number": PHONE,
            "waba_id": "12345",
            "is_on_biz_app": True,
            "coexistence_state": "active",
        }
    ]
    install(monkeypatch, [response(page(accounts)), response(page(phones))])
    report = diagnose(settings(), live=True)
    assert report["checks"]["business_accounts"]["binding"] == "matched"
    phone = report["checks"]["phone_numbers"]
    assert phone["binding"] == "matched"
    assert phone["coexistence"] == "active"
    assert phone["messaging_profile"] == "not_verified"
    assert report["egress_authorized"] is False
    assert PHONE not in json.dumps(report)


@pytest.mark.parametrize(
    "change",
    [
        {"waba_id": "other"},
        {"is_on_biz_app": "true"},
        {"coexistence_state": "syncing"},
        {"coexistence_state": "sync_deadline_expired"},
    ],
)
def test_wrong_binding_or_pending_sync_never_becomes_active(monkeypatch, change):
    phone = {
        "phone_number": PHONE,
        "waba_id": "12345",
        "is_on_biz_app": True,
        "coexistence_state": "active",
        **change,
    }
    install(monkeypatch, [response(page([])), response(page([phone]))])
    report = diagnose(settings(), live=True)
    assert report["checks"]["phone_numbers"]["coexistence"] == "unproven"


@pytest.mark.parametrize(
    "body,state",
    [
        (page([], total_pages=2), "pagination_incomplete"),
        ({"data": []}, "pagination_unproven"),
        (page([], total_pages=True), "response_invalid"),
        ({"data": "private"}, "response_invalid"),
        (b'{"data":[],"data":[{}]}', "response_invalid"),
        (b'{"data":[],"meta":{"total_pages":NaN}}', "response_invalid"),
        (b"x" * 1_048_577, "response_invalid"),
    ],
)
def test_partial_or_malformed_response_does_not_prove_absence(monkeypatch, body, state):
    install(monkeypatch, [response(body)])
    check, data = TelnyxAccountProbe(KEY).read("business_accounts")
    assert check.state == state and data is None


def test_timeout_is_safe_and_does_not_retry(monkeypatch, caplog):
    calls = install(monkeypatch, [requests.Timeout(KEY + PHONE)])
    check, data = TelnyxAccountProbe(KEY).read("business_accounts")
    assert check.state == "network_unavailable" and data is None
    assert len(calls) == 1 and KEY not in caplog.text


def test_only_documented_read_resources_allowed(monkeypatch):
    calls = install(monkeypatch, [])
    with pytest.raises(ValueError, match="unsupported_preflight_resource"):
        TelnyxAccountProbe(KEY).read("https://example.org/collect")
    assert not calls


def test_app_link_is_optional_and_does_not_authorize_signup(monkeypatch):
    calls = install(
        monkeypatch,
        [
            response(page([])),
            response(page([])),
            response({"data": {"app_id": "123", "solution_id": "456", "enabled": True}}),
        ],
    )
    report = diagnose(settings(), live=True, tech_provider=True)
    assert len(calls) == 3
    assert report["checks"]["tech_provider"]["link"] == "observed_enabled"
    assert report["egress_authorized"] is False


def test_settings_repr_and_dump_hide_credentials():
    config = settings()
    assert KEY not in repr(config) + str(config.model_dump())
