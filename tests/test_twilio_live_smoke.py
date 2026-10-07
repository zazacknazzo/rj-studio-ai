from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from requests import Timeout
from twilio.base.exceptions import TwilioRestException
from twilio.request_validator import RequestValidator

from rj_studio_ai.config import Settings
from rj_studio_ai.live_messaging_smoke import LiveSmokeBlocked
from rj_studio_ai.persistence import DeliveryState, SqliteConversationStore
from rj_studio_ai.twilio_live_smoke import TwilioLiveSmoke, main


@pytest.fixture(autouse=True)
def prohibit_uncontrolled_requests(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Smoke tests must not touch the external network")

    monkeypatch.setattr("requests.sessions.Session.send", forbidden)


def smoke_configuration(tmp_path):
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "data" / "normal.db",
        llm_provider="openai",
        openai_api_key="synthetic-openai-key",
        whatsapp_provider="twilio",
        delivery_mode="proactive",
        twilio_account_sid="AC" + "a" * 32,
        twilio_api_key_sid="SK" + "b" * 32,
        twilio_api_key_secret="synthetic-private-key",
        twilio_auth_token="e" * 32,
        twilio_public_webhook_url="https://synthetic.example/webhooks/twilio",
        twilio_status_callback_url="https://synthetic.example/webhooks/twilio/status",
    )
    environment = {
        "TWILIO_AUTH_TOKEN_TRUST": "rotated",
        "TWILIO_SMOKE_SENDER": "+1415000000001",
        "TEST_WHATSAPP_RECIPIENT": "+5511000000001",
        "TWILIO_SMOKE_DATABASE_PATH": str(
            tmp_path / "work" / "twilio-live-smoke" / "first" / "smoke-live-messaging.db"
        ),
    }
    return settings, environment


def test_trusted_valid_configuration_without_opt_in_is_ready_but_never_starts(tmp_path):
    settings, environment = smoke_configuration(tmp_path)
    driver = TwilioLiveSmoke(settings, environment, project_root=tmp_path)
    result = driver.preflight()
    assert result["status"] == "READY_FOR_LIVE_SMOKE / AWAITING_OPERATOR_OPT_IN"
    assert result["checks"]["adapter_config"]
    assert not result["checks"]["opt_in"]
    assert not (tmp_path / "work").exists()


@pytest.mark.parametrize(
    ("field", "value", "check"),
    [
        ("twilio_account_sid", "", "adapter_config"),
        ("twilio_api_key_sid", "invalid", "adapter_config"),
        ("twilio_api_key_secret", "", "adapter_config"),
        ("twilio_auth_token", "", "auth_token_format"),
        ("twilio_validate_signature", False, "signature_validation"),
        ("twilio_public_webhook_url", "http://synthetic.example/webhooks/twilio", "callback_urls"),
        (
            "twilio_status_callback_url",
            "https://other.example/webhooks/twilio/status",
            "callback_urls",
        ),
        ("openai_reasoning_effort", "medium", "frozen_candidate"),
    ],
)
def test_invalid_adapter_configuration_is_blocked_before_any_network_or_database(
    tmp_path, field, value, check
):
    settings, environment = smoke_configuration(tmp_path)
    setattr(settings, field, value)
    calls = []
    driver = TwilioLiveSmoke(
        settings,
        environment,
        project_root=tmp_path,
        client_factory=lambda _: calls.append("network"),
    )
    result = driver.preflight()
    assert result["status"] == "BLOCKED_INVALID_CONFIGURATION"
    assert not result["checks"][check]
    assert calls == []
    assert not (tmp_path / "work").exists()


def test_one_manual_outbox_submission_persists_acceptance_without_executors_or_llm(tmp_path):
    settings, environment = smoke_configuration(tmp_path)
    environment["ALLOW_LIVE_MESSAGING_SMOKE"] = "1"
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(sid="SM" + "c" * 32, status="queued")

    driver = TwilioLiveSmoke(
        settings,
        environment,
        project_root=tmp_path,
        client_factory=lambda _: SimpleNamespace(messages=SimpleNamespace(create=create)),
    )
    with TestClient(driver.prepare()) as client:
        driver.verify_public_callback(get=lambda *args, **kwargs: client.get("/health"))
        result = driver.submit_once()
        assert result["provider_acceptance"]
        assert result["submissions"] == 1
        assert result["final_state"] == "accepted"
        assert result["retries"] == 0
        assert result["result_class"] == "accepted_callback_pending"
        assert "SM" + "c" * 32 not in str(result)
        with pytest.raises(LiveSmokeBlocked, match="smoke_submission_limit"):
            driver.submit_once()
    assert len(calls) == 1
    assert calls[0]["body"] == "Teste RJ Studio AI"
    path = tmp_path / "work" / "twilio-live-smoke" / "first" / "smoke-live-messaging.db"
    store = SqliteConversationStore(path)
    history = store.get_history(provider="twilio", customer_address="whatsapp:+5511000000001")
    assert len(history) == 2
    delivery = store.get_delivery_for_provider_inbound(
        provider="twilio", provider_message_id="SM" + driver.smoke_id
    )
    assert delivery.state == DeliveryState.ACCEPTED
    assert delivery.provider_message_id is not None
    assert store.get_generation_metrics(inbound_message_id=delivery.inbound_message_id) == []


@pytest.mark.parametrize("trust", ["", "old", "unknown", " rotated "])
def test_trust_marker_is_operator_attestation_and_never_inferred_from_present_credentials(
    tmp_path, trust
):
    settings, environment = smoke_configuration(tmp_path)
    environment["TWILIO_AUTH_TOKEN_TRUST"] = trust
    assert TwilioLiveSmoke(settings, environment, project_root=tmp_path).preflight()["status"] == (
        "BLOCKED_PENDING_TOKEN_ROTATION"
    )


@pytest.mark.parametrize("recipient", ["", "last-customer", "+1415000000001"])
def test_recipient_must_be_explicit_valid_and_different_from_sender(tmp_path, recipient):
    settings, environment = smoke_configuration(tmp_path)
    environment["TEST_WHATSAPP_RECIPIENT"] = recipient
    result = TwilioLiveSmoke(settings, environment, project_root=tmp_path).preflight()
    assert result["status"] == "BLOCKED_INVALID_CONFIGURATION"


def test_existing_database_and_normal_database_are_never_reused(tmp_path):
    settings, environment = smoke_configuration(tmp_path)
    environment["TWILIO_SMOKE_DATABASE_PATH"] = str(settings.database_path)
    assert not TwilioLiveSmoke(settings, environment, project_root=tmp_path).preflight()["checks"][
        "isolated_fresh_database"
    ]
    _, environment = smoke_configuration(tmp_path)
    path = tmp_path / "work" / "twilio-live-smoke" / "first" / "smoke-live-messaging.db"
    path.parent.mkdir(parents=True)
    path.write_text("do not overwrite synthetic historical evidence")
    assert not TwilioLiveSmoke(settings, environment, project_root=tmp_path).preflight()["checks"][
        "isolated_fresh_database"
    ]
    assert path.read_text() == "do not overwrite synthetic historical evidence"


def test_symlink_cannot_redirect_the_database_to_normal_data(tmp_path):
    settings, environment = smoke_configuration(tmp_path)
    path = tmp_path / "work" / "twilio-live-smoke" / "first"
    path.parent.mkdir(parents=True)
    settings.database_path.parent.mkdir(parents=True)
    path.symlink_to(settings.database_path.parent, target_is_directory=True)
    result = TwilioLiveSmoke(settings, environment, project_root=tmp_path).preflight()
    assert not result["checks"]["isolated_fresh_database"]


def test_malformed_url_fails_closed_without_echoing_it(tmp_path):
    settings, environment = smoke_configuration(tmp_path)
    settings.twilio_public_webhook_url = "https://[synthetic-private-key"
    result = TwilioLiveSmoke(settings, environment, project_root=tmp_path).preflight()
    assert not result["checks"]["callback_urls"]
    assert "synthetic-private-key" not in str(result)


def test_prepare_requires_opt_in_and_reserves_one_empty_isolated_database(tmp_path):
    settings, environment = smoke_configuration(tmp_path)
    driver = TwilioLiveSmoke(settings, environment, project_root=tmp_path)
    with pytest.raises(LiveSmokeBlocked):
        driver.prepare()
    assert not (tmp_path / "work").exists()
    environment["ALLOW_LIVE_MESSAGING_SMOKE"] = "1"
    driver = TwilioLiveSmoke(settings, environment, project_root=tmp_path)
    driver.prepare()
    path = tmp_path / "work" / "twilio-live-smoke" / "first" / "smoke-live-messaging.db"
    store = SqliteConversationStore(path)
    assert store.migrations_are_current()
    assert store.list_pending_generations() == []
    assert store.get_history(provider="twilio", customer_address="whatsapp:+5511000000001") == []
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(LiveSmokeBlocked):
        driver.prepare()
    restarted = TwilioLiveSmoke(settings, environment, project_root=tmp_path)
    with pytest.raises(LiveSmokeBlocked):
        restarted.prepare()


def test_public_https_must_reach_this_smoke_before_submission(tmp_path):
    settings, environment = smoke_configuration(tmp_path)
    environment["ALLOW_LIVE_MESSAGING_SMOKE"] = "1"
    calls = []
    driver = TwilioLiveSmoke(
        settings,
        environment,
        project_root=tmp_path,
        client_factory=lambda _: calls.append("Twilio"),
    )
    with TestClient(driver.prepare()) as client:
        with pytest.raises(LiveSmokeBlocked, match="smoke_callback_not_verified"):
            driver.submit_once()
        with pytest.raises(LiveSmokeBlocked, match="smoke_public_callback_not_verified"):
            driver.verify_public_callback(
                get=lambda *args, **kwargs: SimpleNamespace(
                    status_code=200, json=lambda: {"status": "ok", "smoke_id": "another-app"}
                )
            )
        checks = []

        def public_get(url, **kwargs):
            checks.append(kwargs)
            return client.get("/health")

        driver.verify_public_callback(get=public_get)
        assert checks[0]["verify"] is True
        assert checks[0]["allow_redirects"] is False
        assert checks[0]["timeout"] == (3, 5)
    assert calls == []


def signed_callback(client, settings, status, *, valid=True):
    form = {"MessageSid": "SM" + "c" * 32, "MessageStatus": status, "FutureField": "ignored"}
    signature = RequestValidator(settings.twilio_auth_token).compute_signature(
        settings.twilio_status_callback_url, form
    )
    return client.post(
        "/webhooks/twilio/status",
        data=form,
        headers={"X-Twilio-Signature": signature if valid else "invalid"},
    )


def test_early_callback_duplicate_and_reordered_statuses_use_durable_core(tmp_path):
    settings, environment = smoke_configuration(tmp_path)
    environment["ALLOW_LIVE_MESSAGING_SMOKE"] = "1"
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        assert signed_callback(client, settings, "sent").status_code == 200
        return SimpleNamespace(sid="SM" + "c" * 32, status="queued")

    driver = TwilioLiveSmoke(
        settings,
        environment,
        project_root=tmp_path,
        client_factory=lambda _: SimpleNamespace(messages=SimpleNamespace(create=create)),
    )
    with TestClient(driver.prepare()) as client:
        assert client.get("/ready").status_code == 200
        driver.verify_public_callback(get=lambda *args, **kwargs: client.get("/health"))
        assert driver.submit_once()["final_state"] == "sent"
        for status in ["delivered", "read", "read", "sent", "future-unrecognized"]:
            assert signed_callback(client, settings, status).status_code == 200
        result = driver.report()
        assert result["status"] == "LIVE_SMOKE_PASS"
        assert result["final_state"] == "read"
        assert result["duplicate_callbacks"] == 2
        assert result["ignored_callbacks"] == 1
        assert result["retries"] == result["duplicate_sends"] == 0
        assert len(calls) == 1


def test_invalid_callback_blocks_submission_and_unsigned_data_is_never_persisted(tmp_path):
    settings, environment = smoke_configuration(tmp_path)
    environment["ALLOW_LIVE_MESSAGING_SMOKE"] = "1"
    calls = []
    driver = TwilioLiveSmoke(
        settings,
        environment,
        project_root=tmp_path,
        client_factory=lambda _: calls.append("Twilio"),
    )
    with TestClient(driver.prepare()) as client:
        driver.verify_public_callback(get=lambda *args, **kwargs: client.get("/health"))
        assert signed_callback(client, settings, "read", valid=False).status_code == 403
        with pytest.raises(LiveSmokeBlocked, match="smoke_callback_invalid"):
            driver.submit_once()
    assert calls == []


@pytest.mark.parametrize("failure", ["timeout", "rate-limit", "permanent"])
def test_any_submission_failure_stops_without_retry_and_restart_cannot_send_again(
    tmp_path, failure, caplog
):
    settings, environment = smoke_configuration(tmp_path)
    environment["ALLOW_LIVE_MESSAGING_SMOKE"] = "1"
    calls = []

    def create(**kwargs):
        calls.append("submission")
        if failure == "timeout":
            raise Timeout("synthetic-private-key")
        raise TwilioRestException(
            429 if failure == "rate-limit" else 401,
            "https://synthetic.example",
            msg="synthetic-private-key",
            code=20429 if failure == "rate-limit" else 20003,
        )

    def factory(_):
        return SimpleNamespace(messages=SimpleNamespace(create=create))

    driver = TwilioLiveSmoke(settings, environment, project_root=tmp_path, client_factory=factory)
    with TestClient(driver.prepare()) as client:
        driver.verify_public_callback(get=lambda *args, **kwargs: client.get("/health"))
        result = driver.submit_once()
        assert result["final_state"] == ("unknown" if failure == "timeout" else "failed")
        assert not result["provider_acceptance"]
        assert result["submissions"] == 1
        assert result["retries"] == 0
        assert "synthetic-private-key" not in str(result) + caplog.text
        with pytest.raises(LiveSmokeBlocked):
            driver.submit_once()
    restarted = TwilioLiveSmoke(
        settings, environment, project_root=tmp_path, client_factory=factory
    )
    with pytest.raises(LiveSmokeBlocked):
        restarted.prepare()
    assert len(calls) == 1


def test_two_process_equivalent_drivers_cannot_reserve_the_same_smoke_database(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    settings, environment = smoke_configuration(tmp_path)
    environment["ALLOW_LIVE_MESSAGING_SMOKE"] = "1"

    def reserve(_):
        driver = TwilioLiveSmoke(settings, environment, project_root=tmp_path)
        try:
            driver.prepare()
            return True
        except LiveSmokeBlocked:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, range(2))) == [False, True]


def test_report_and_preflight_have_no_phone_credential_or_full_provider_identifier(tmp_path):
    settings, environment = smoke_configuration(tmp_path)
    environment["ALLOW_LIVE_MESSAGING_SMOKE"] = "1"
    driver = TwilioLiveSmoke(
        settings,
        environment,
        project_root=tmp_path,
        client_factory=lambda _: SimpleNamespace(
            messages=SimpleNamespace(create=lambda **_: SimpleNamespace(sid="SM" + "c" * 32))
        ),
    )
    with TestClient(driver.prepare()) as client:
        driver.verify_public_callback(get=lambda *args, **kwargs: client.get("/health"))
        result = driver.submit_once()
    private = [
        environment["TEST_WHATSAPP_RECIPIENT"],
        environment["TWILIO_SMOKE_SENDER"],
        settings.twilio_auth_token,
        settings.twilio_api_key_secret,
        settings.twilio_account_sid,
        "SM" + "c" * 32,
    ]
    assert not any(value in str(result) + repr(driver) for value in private)


def test_check_only_cli_refuses_unverified_trust_and_does_not_create_or_send(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN_TRUST", raising=False)
    monkeypatch.delenv("ALLOW_LIVE_MESSAGING_SMOKE", raising=False)
    config = tmp_path / ".env"
    config.write_text(
        "TWILIO_AUTH_TOKEN=" + "e" * 32 + "\nTWILIO_API_KEY_SECRET=synthetic-private-key\n"
    )
    assert main(["--check", "--env-file", str(config)]) == 2
    output = capsys.readouterr().out
    assert "BLOCKED_PENDING_TOKEN_ROTATION" in output
    assert "synthetic-private-key" not in output
    assert "e" * 32 not in output
    assert not (tmp_path / "work").exists()


def test_config_validation_failure_cli_is_redacted(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OUTBOUND_REQUEST_TIMEOUT_SECONDS", raising=False)
    config = tmp_path / ".env"
    config.write_text("OUTBOUND_REQUEST_TIMEOUT_SECONDS=synthetic-private-key\n")
    assert main(["--check", "--env-file", str(config)]) == 2
    output = capsys.readouterr().out
    assert "synthetic-private-key" not in output
    assert "smoke_operation_failed" in output


def test_lost_local_acceptance_commit_is_reported_ambiguous_and_never_retried(tmp_path):
    import sqlite3

    from rj_studio_ai.persistence import PersistenceUnavailable

    settings, environment = smoke_configuration(tmp_path)
    environment["ALLOW_LIVE_MESSAGING_SMOKE"] = "1"
    calls = []

    def create(**kwargs):
        calls.append("submission")
        return SimpleNamespace(sid="SM" + "c" * 32)

    driver = TwilioLiveSmoke(
        settings,
        environment,
        project_root=tmp_path,
        client_factory=lambda _: SimpleNamespace(messages=SimpleNamespace(create=create)),
    )
    with TestClient(driver.prepare()) as client:
        with sqlite3.connect(environment["TWILIO_SMOKE_DATABASE_PATH"]) as connection:
            connection.execute("""CREATE TRIGGER reject_acceptance
                BEFORE UPDATE ON outbound_deliveries
                WHEN NEW.state='accepted' BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
        driver.verify_public_callback(get=lambda *args, **kwargs: client.get("/health"))
        with pytest.raises(PersistenceUnavailable):
            driver.submit_once()
        result = driver.report()
        assert result["result_class"] == "outcome_unknown"
        assert result["provider_acceptance"] is None
        assert result["final_state"] == "sending"
        with pytest.raises(LiveSmokeBlocked):
            driver.submit_once()
    assert len(calls) == 1


def test_invalid_callback_during_sdk_setup_is_fenced_at_external_submission(tmp_path):
    settings, environment = smoke_configuration(tmp_path)
    environment["ALLOW_LIVE_MESSAGING_SMOKE"] = "1"
    calls = []

    def create(**kwargs):
        calls.append("external-submission")
        return SimpleNamespace(sid="SM" + "c" * 32)

    def factory(_):
        assert signed_callback(client, settings, "read", valid=False).status_code == 403
        return SimpleNamespace(messages=SimpleNamespace(create=create))

    driver = TwilioLiveSmoke(settings, environment, project_root=tmp_path, client_factory=factory)
    with TestClient(driver.prepare()) as client:
        driver.verify_public_callback(get=lambda *args, **kwargs: client.get("/health"))
        result = driver.submit_once()
        assert result["status"] == "LIVE_SMOKE_FAIL"
        assert result["submissions"] == 0
    assert calls == []


def test_failed_callback_and_concurrent_report_snapshots_cannot_yield_false_pass(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    settings, environment = smoke_configuration(tmp_path)
    environment["ALLOW_LIVE_MESSAGING_SMOKE"] = "1"
    driver = TwilioLiveSmoke(
        settings,
        environment,
        project_root=tmp_path,
        client_factory=lambda _: SimpleNamespace(
            messages=SimpleNamespace(create=lambda **_: SimpleNamespace(sid="SM" + "c" * 32))
        ),
    )
    with TestClient(driver.prepare()) as client:
        driver.verify_public_callback(get=lambda *args, **kwargs: client.get("/health"))
        driver.submit_once()
        assert signed_callback(client, settings, "sent").status_code == 200
        with ThreadPoolExecutor(max_workers=2) as pool:
            failure = pool.submit(signed_callback, client, settings, "failed")
            reports = list(pool.map(lambda _: driver.report(), range(100)))
            assert failure.result().status_code == 200
        for result in reports:
            if "failed" in result["callbacks"] or result["final_state"] == "failed":
                assert result["status"] == "LIVE_SMOKE_FAIL"
        final = driver.report()
        assert final["result_class"] == "delivery_failed"
        assert final["final_state"] == "failed"
        assert final["provider_acceptance"]
        assert final["submissions"] == 1
