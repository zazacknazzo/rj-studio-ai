"""Authenticated Cloudflare authority; no credentials or raw Messages reach logs."""

import hashlib
import hmac
import json
import re
from contextlib import nullcontext
from dataclasses import dataclass, field
from threading import RLock
from time import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from rj_studio_ai.persistence import PersistenceUnavailable


class AuthorityClosed(PersistenceUnavailable):
    """An authority failure never grants transport or implies non-submission."""


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


@dataclass(frozen=True)
class AuthorityConfig:
    url: str
    scope: str
    account: str
    witness_account: str
    public_key: str
    runtime_key: str = field(repr=False)

    def __post_init__(self):
        url = urlsplit(self.url)
        if (
            url.scheme != "https"
            or not url.hostname
            or not url.hostname.endswith(".workers.dev")
            or url.path != "/command"
            or url.port not in (None, 443)
            or url.username
            or url.password
            or url.query
            or url.fragment
            or not re.fullmatch(r"[a-f0-9]{64}", self.scope)
            or not re.fullmatch(r"[a-f0-9]{64}", self.public_key)
            or not re.fullmatch(r"[a-f0-9]{32}", self.account)
            or not re.fullmatch(r"[a-f0-9]{32}", self.witness_account)
            or self.account == self.witness_account
            or len(self.runtime_key) < 32
        ):
            raise ValueError("independent_authority_configuration_required")


class CloudflareAuthority:
    """Challenge-bound signatures, monotonic reads and CAS; never retries commands."""

    def __init__(self, config, *, client=None, clock=time):
        self.config, self.client, self.clock = config, client, clock
        self.lock = RLock()
        self.state = None
        self.boot_id = uuid4().hex
        self.epoch = None

    def _exchange(self, action, args, *, expected=None, operator_key=None):
        nonce = uuid4().hex
        command = {
            "v": 1,
            "scope": self.config.scope,
            "nonce": nonce,
            "time": int(self.clock() * 1000),
            "action": action,
            "args": args,
        }
        if expected is not None:
            command["expected"] = expected
        wire = encoded(command)
        key = operator_key or self.config.runtime_key
        try:
            with (
                (
                    httpx.Client(trust_env=False)
                    if self.client is None
                    else nullcontext(self.client)
                ) as client,
                client.stream(
                    "POST",
                    self.config.url,
                    content=wire,
                    headers={
                        "content-type": "application/json",
                        "x-livia-role": "operator" if operator_key else "runtime",
                        "x-livia-signature": hmac.new(
                            key.encode(), wire, hashlib.sha256
                        ).hexdigest(),
                    },
                    timeout=6,
                    follow_redirects=False,
                ) as response,
            ):
                body = bytearray()
                for chunk in response.iter_bytes():
                    if len(body) + len(chunk) > 32768:
                        raise ValueError()
                    body.extend(chunk)
                if response.status_code not in (200, 409):
                    raise ValueError()
            raw = json.loads(body)
            payload = raw["payload"]
            signature = raw["signature"]
            if not isinstance(signature, str) or not re.fullmatch(r"[a-f0-9]{128}", signature):
                raise ValueError()
            VerifyKey(bytes.fromhex(self.config.public_key)).verify(
                encoded(payload), bytes.fromhex(signature)
            )
            if (
                payload["v"] != 1
                or payload["scope"] != self.config.scope
                or payload["account"] != self.config.account
                or payload["nonce"] != nonce
                or type(payload["served_at"]) is not int
                or abs(payload["served_at"] - self.clock() * 1000) > 15000
            ):
                raise ValueError()
            if payload.get("ok") is not True:
                code = payload.get("error")
                if isinstance(code, str) and re.fullmatch(r"[a-z_]{3,80}", code):
                    raise AuthorityClosed(code)
                raise ValueError()
            state = payload["state"]
            if (
                state["scope"] != self.config.scope
                or type(state["revision"]) is not int
                or type(state["epoch"]) is not int
                or not 0 <= state["epoch"] <= state["revision"]
                or payload["digest"] != digest(state)
                or (
                    self.state is not None
                    and (
                        state["epoch"] < self.state["epoch"]
                        or state["revision"] < self.state["revision"]
                        or (
                            state["revision"] == self.state["revision"]
                            and digest(state) != digest(self.state)
                        )
                    )
                )
            ):
                raise ValueError()
        except AuthorityClosed:
            raise
        except (httpx.HTTPError, BadSignatureError, ValueError, KeyError, TypeError):
            raise AuthorityClosed("authority_response_unverified") from None
        self.state = state
        return state

    def read(self):
        with self.lock:
            return self._exchange("read", {})

    def command(self, action, args, *, operator_key=None):
        with self.lock:
            # This revision is only an optimistic CAS expectation, never a cached
            # permission. The Worker rechecks its live independent witness before
            # every command; any intervening operator mutation denies this CAS.
            prior = self.state if self.state is not None else self.read()
            state = self._exchange(
                action, args, expected=prior["revision"], operator_key=operator_key
            )
            if action != "check_submission" and state["revision"] != prior["revision"] + 1:
                raise AuthorityClosed("authority_commit_unverified")
            return state

    def boot(self, head, sequence):
        with self.lock:
            state = self.command("boot", {"boot": self.boot_id, "head": head, "sequence": sequence})
            if state["boot"] != self.boot_id or not state["paused"] or not state["killed"]:
                raise AuthorityClosed("authority_boot_unverified")
            self.epoch = state["epoch"]

    def current(self):
        state = self.read()
        if state["boot"] != self.boot_id or state["epoch"] != self.epoch:
            raise AuthorityClosed("authority_boot_superseded")
        return state

    def runtime_command(self, action, **args):
        with self.lock:
            if (
                self.state is None
                or self.state["boot"] != self.boot_id
                or self.state["epoch"] != self.epoch
            ):
                raise AuthorityClosed("authority_boot_superseded")
            return self.command(action, {"boot": self.boot_id, "epoch": self.epoch, **args})

    def advance(self, prior, head, sequence, entry):
        return self.runtime_command(
            "advance",
            prior=prior,
            head=head,
            sequence=sequence,
            kind=entry["kind"],
            **({"participant": entry["participant_hash"]} if entry["kind"] == "revoke" else {}),
        )
