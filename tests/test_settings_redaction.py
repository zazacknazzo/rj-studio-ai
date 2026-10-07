import json
import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from rj_studio_ai.config import Settings
from rj_studio_ai.main import create_app

SECRET_FIELDS = (
    "openai_api_key",
    "anthropic_api_key",
    "twilio_account_sid",
    "twilio_auth_token",
    "twilio_api_key_sid",
    "twilio_api_key_secret",
    "meta_whatsapp_access_token",
    "meta_whatsapp_app_secret",
    "meta_whatsapp_verify_token",
)


def synthetic_secrets():
    return {field: "synthetic-private-" + field for field in SECRET_FIELDS}


def contains_private_value(text):
    return any(value in text for value in synthetic_secrets().values())


def test_settings_repr_and_serialization_redact_credentials_but_preserve_internal_access():
    settings = Settings(_env_file=None, **synthetic_secrets())
    assert not contains_private_value(repr(settings))
    assert not contains_private_value(str(settings))
    assert not contains_private_value(settings.model_dump_json())
    assert not contains_private_value(json.dumps(settings.model_dump(mode="json")))
    assert not set(SECRET_FIELDS).intersection(settings.model_dump())
    assert settings.model_dump()["llm_provider"] == "fixed"
    assert settings.model_dump()["app_name"] == "RJ Studio AI"
    assert all(getattr(settings, key) == value for key, value in synthetic_secrets().items())


def test_configuration_error_messages_and_debug_errors_do_not_echo_private_inputs():
    try:
        Settings(_env_file=None, llm_provider="synthetic-private-openai_api_key")
    except ValidationError as error:
        assert not contains_private_value(str(error))
        assert not contains_private_value(repr(error))
        assert not contains_private_value(error.json())
        assert not contains_private_value(str(error.errors()))
    else:
        raise AssertionError("Invalid provider must still fail validation")


def test_startup_debug_logging_remains_redacted(tmp_path, caplog):
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "synthetic.db",
        twilio_validate_signature=False,
        **synthetic_secrets(),
    )
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("synthetic-startup").debug("Startup settings: %r", settings)
        with TestClient(create_app(settings)) as client:
            assert client.get("/health").status_code == 200
    assert "Startup settings:" in caplog.text
    assert not contains_private_value(caplog.text)


@pytest.mark.parametrize("factory", [Settings, Settings.model_validate])
def test_invalid_private_values_are_removed_from_structured_validation_evidence(factory):
    values = {
        "_env_file": None,
        "outbound_request_timeout_seconds": "synthetic-private-openai_api_key",
        "twilio_auth_token": {"invalid": "synthetic-private-twilio_auth_token"},
    }
    with pytest.raises(ValidationError) as captured:
        factory(**values) if factory is Settings else factory(values)
    assert not contains_private_value(captured.value.json())
    assert not contains_private_value(str(captured.value.errors()))
    assert len(captured.value.errors()) == 2


def test_numeric_constraints_and_nonsecret_diagnostics_are_preserved():
    with pytest.raises(ValidationError) as captured:
        Settings(_env_file=None, outbound_request_timeout_seconds=0)
    assert captured.value.errors()[0]["type"] == "greater_than"
    assert captured.value.errors()[0]["loc"] == ("outbound_request_timeout_seconds",)
