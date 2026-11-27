"""Read-only account diagnosis. This module cannot authorize or send messages."""

import argparse
import json
import re
from dataclasses import dataclass

import requests
from pydantic import Field

from rj_studio_ai.config import Settings

_BASE = "https://api.telnyx.com/v2/whatsapp/"
_RESOURCES = frozenset({"business_accounts", "phone_numbers", "foreign_apps"})
_MAX_BYTES = 1_048_576


class PreflightSettings(Settings):
    telnyx_api_key: str = Field(default="", repr=False, exclude=True)


@dataclass(frozen=True, slots=True)
class Check:
    state: str
    observed_count: int | None = None


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject_constant(_):
    raise ValueError


class TelnyxAccountProbe:
    """Only fixed read endpoints; response data stays within the backend process."""

    def __init__(self, api_key: str):
        self._api_key = api_key

    def read(self, resource: str):
        if resource not in _RESOURCES:
            raise ValueError("unsupported_preflight_resource")
        if not self._api_key:
            return Check("credential_missing"), None
        if not re.fullmatch(r"[\x21-\x7e]{1,4096}", self._api_key):
            return Check("credential_invalid"), None
        try:
            with requests.Session() as session:
                session.trust_env = False
                with session.get(
                    _BASE + resource,
                    headers={"Authorization": "Bearer " + self._api_key},
                    timeout=(5, 10),
                    allow_redirects=False,
                    stream=True,
                ) as response:
                    if response.status_code != 200:
                        state = {
                            401: "authentication_denied",
                            403: "permission_denied",
                            404: "resource_unavailable",
                            429: "rate_limited",
                        }.get(response.status_code, "http_unavailable")
                        return Check(state), None
                    if (
                        response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                        != "application/json"
                    ):
                        return Check("response_invalid"), None
                    content = bytearray()
                    for chunk in response.iter_content(16_384):
                        content.extend(chunk)
                        if len(content) > _MAX_BYTES:
                            return Check("response_invalid"), None
                    body = json.loads(
                        content.decode("utf-8"),
                        object_pairs_hook=_unique,
                        parse_constant=_reject_constant,
                    )
                    if not isinstance(body, dict) or body.get("errors"):
                        return Check("response_invalid"), None
                    data = body["data"]
                    if resource == "foreign_apps":
                        if not isinstance(data, dict):
                            return Check("response_invalid"), None
                        return Check("observed"), data
                    if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
                        return Check("response_invalid"), None
                    meta = body.get("meta")
                    if meta is None:
                        return Check("pagination_unproven", len(data)), None
                    if not isinstance(meta, dict):
                        return Check("response_invalid"), None
                    pages = meta.get("total_pages")
                    if type(pages) is not int or pages < 0:
                        return Check("response_invalid"), None
                    if pages > 1:
                        return Check("pagination_incomplete", len(data)), None
                    return Check("observed", len(data)), data
        except requests.RequestException:
            return Check("network_unavailable"), None
        except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
            return Check("response_invalid"), None


def diagnose(settings: PreflightSettings, *, live=False, tech_provider=False):
    """Safe summary only. Observation never implies permission to send."""
    report = {
        "mode": "read_only_live" if live else "configuration_only",
        "egress_authorized": False,
        "configuration": {
            name: bool(getattr(settings, "telnyx_" + name))
            for name in (
                "api_key",
                "public_key",
                "phone_number",
                "messaging_profile_id",
                "waba_id",
                "organization_id",
            )
        },
        "checks": {},
    }
    if not live:
        return report
    probe = TelnyxAccountProbe(settings.telnyx_api_key)
    checks = report["checks"]
    for resource in ("business_accounts", "phone_numbers"):
        check, data = probe.read(resource)
        summary = {"state": check.state, "observed_count": check.observed_count}
        checks[resource] = summary
        if data is None:
            continue
        if resource == "business_accounts":
            if not settings.telnyx_waba_id:
                summary["binding"] = "not_configured"
                continue
            matches = [row for row in data if row.get("waba_id") == settings.telnyx_waba_id]
            summary["binding"] = "matched" if len(matches) == 1 else "unproven"
        else:
            if not all((settings.telnyx_phone_number, settings.telnyx_waba_id)):
                summary["binding"] = "not_configured"
                continue
            matches = [
                row for row in data if row.get("phone_number") == settings.telnyx_phone_number
            ]
            matched = len(matches) == 1 and matches[0].get("waba_id") == settings.telnyx_waba_id
            summary["binding"] = "matched" if matched else "unproven"
            summary["coexistence"] = (
                "active"
                if matched
                and matches[0].get("is_on_biz_app") is True
                and matches[0].get("coexistence_state") == "active"
                else "unproven"
            )
            # This endpoint does not document a messaging_profile_id field.
            # Its local presence must never be described as remotely verified.
            summary["messaging_profile"] = "not_verified"
    if tech_provider:
        check, data = probe.read("foreign_apps")
        checks["tech_provider"] = {
            "state": check.state,
            "link": "observed_enabled"
            if data
            and data.get("enabled") is True
            and isinstance(data.get("app_id"), str)
            and bool(data["app_id"])
            and isinstance(data.get("solution_id"), str)
            and bool(data["solution_id"])
            else "unproven",
        }
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--live", action="store_true", help="Read the account through fixed GETs")
    parser.add_argument("--tech-provider", action="store_true", help="Also inspect the app link")
    args = parser.parse_args(argv)
    try:
        report = diagnose(
            PreflightSettings(_env_file=args.env_file),
            live=args.live,
            tech_provider=args.tech_provider,
        )
    except (ValueError, OSError):
        print(json.dumps({"error": "configuration_invalid", "egress_authorized": False}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
