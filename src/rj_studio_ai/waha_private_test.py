"""Explicit bounded private test. Same-host rollback risk was accepted by the user.

This is not the independent B3 authority and never closes AUD-01/AR-02.
The canonical strict store/sender keep identity, consent, handoff and unknown fences.
"""

import hashlib
import hmac
import json
import os
from copy import deepcopy
from pathlib import Path
from threading import RLock
from time import monotonic, time
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException, Request

from rj_studio_ai.delivery import OutboundDeliveryExecutor
from rj_studio_ai.waha_authority import AuthorityClosed, encoded
from rj_studio_ai.waha_cloudflare import (
    AnchoredWahaJournal,
    AuthorizedWahaSender,
    CloudflareWahaStore,
)
from rj_studio_ai.waha_live import WahaSettings, build_waha_pipeline, create_waha_app


def require(value, message):
    if not value:
        raise AuthorityClosed(message)


class LocalTestAuthority:
    """HMAC/fsync ledger; protects ordinary restarts, NOT joint backup rollback."""

    def __init__(self, path, *, key, scope):
        self.path, self.key = Path(path), key.encode()
        self.config = SimpleNamespace(scope=scope)
        self.lock, self.state = RLock(), None
        self.boot_id, self.epoch = uuid4().hex, None
        self.last_mac = "0" * 64
        self.submission_valid_until = None

    @classmethod
    def prepare(
        cls, path, *, key, scope, head, sequence, participant, deadline, audience="allowlist"
    ):
        require(audience in {"allowlist", "all_direct"}, "invalid_audience")
        authority = cls(path, key=key, scope=scope)
        authority.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        state = dict(
            revision=0,
            epoch=0,
            boot=None,
            scope=scope,
            head=head,
            sequence=sequence,
            paused=True,
            killed=True,
            enabled=False,
            revoked=[],
            intents={},
            grant=None,
            participant=participant,
            audience=audience,
            deadline=deadline,
        )
        authority._append(state, exclusive=True)
        return authority

    def _append(self, state, *, exclusive=False):
        unsigned = {"prior": self.last_mac, "state": state}
        mac = hmac.new(self.key, encoded(unsigned), hashlib.sha256).hexdigest()
        flags = os.O_WRONLY | (os.O_CREAT | os.O_EXCL if exclusive else os.O_APPEND)
        fd = os.open(self.path, flags, 0o600)
        with os.fdopen(fd, "ab") as file:
            file.write(encoded({**unsigned, "mac": mac}) + b"\n")
            file.flush()
            os.fsync(file.fileno())
        if exclusive:
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        self.state, self.last_mac = deepcopy(state), mac

    def read(self):
        with self.lock:
            try:
                require(
                    self.path.is_file() and not self.path.stat().st_mode & 0o077,
                    "private_test_ledger_missing_or_insecure",
                )
                prior, state = "0" * 64, None
                for revision, line in enumerate(self.path.read_bytes().splitlines()):
                    record = json.loads(line)
                    unsigned = {k: record[k] for k in ("prior", "state")}
                    mac = hmac.new(self.key, encoded(unsigned), hashlib.sha256).hexdigest()
                    require(
                        record["prior"] == prior
                        and hmac.compare_digest(mac, record["mac"])
                        and record["state"]["revision"] == revision
                        and record["state"]["scope"] == self.config.scope,
                        "private_test_ledger_integrity",
                    )
                    state, prior = record["state"], mac
                require(state is not None, "private_test_ledger_empty")
                if self.state is not None:
                    require(
                        state["revision"] >= self.state["revision"]
                        and (state["revision"] != self.state["revision"] or prior == self.last_mac),
                        "private_test_live_rollback",
                    )
                self.state, self.last_mac = state, prior
                return deepcopy(state)
            except (OSError, ValueError, KeyError, TypeError):
                raise AuthorityClosed("private_test_ledger_unverified") from None

    def _change(self, mutation):
        with self.lock:
            state = self.read()
            next_state = deepcopy(state)
            mutation(next_state)
            next_state["revision"] += 1
            self._append(next_state)
            return deepcopy(next_state)

    def boot(self, head, sequence):
        def mutate(s):
            require((s["head"], s["sequence"]) == (head, sequence), "private_test_local_restore")
            s.update(
                epoch=s["epoch"] + 1,
                boot=self.boot_id,
                paused=True,
                killed=True,
                enabled=False,
                grant=None,
            )

        self.epoch = self._change(mutate)["epoch"]

    def current(self):
        state = self.read()
        require(
            state["boot"] == self.boot_id and state["epoch"] == self.epoch,
            "private_test_boot_superseded",
        )
        return state

    @staticmethod
    def active(s):
        return (
            s["enabled"]
            and not s["paused"]
            and not s["killed"]
            and s["deadline"] > time() * 1000
            and len(s["intents"]) < 20
            and not any(v["outcome"] == "unknown" for v in s["intents"].values())
        )

    def activate(self):
        def mutate(s):
            require(
                s["boot"] == self.boot_id
                and s["epoch"] == self.epoch
                and s["deadline"] > time() * 1000
                and len(s["intents"]) < 20
                and (
                    s.get("audience", "allowlist") == "all_direct"
                    or s["participant"] not in s["revoked"]
                )
                and not any(v["outcome"] == "unknown" for v in s["intents"].values()),
                "private_test_activation_denied",
            )
            s.update(enabled=True, paused=False, killed=False, grant=None)

        return self._change(mutate)

    @staticmethod
    def permits_participant(state, participant):
        return (
            isinstance(participant, str)
            and len(participant) == 64
            and participant not in state["revoked"]
            and (
                state.get("audience", "allowlist") == "all_direct"
                or participant == state["participant"]
            )
        )

    def permit(self, intent, participant, head):
        def mutate(s):
            require(
                self.active(s)
                and s["head"] == head
                and s["boot"] == self.boot_id
                and self.permits_participant(s, participant),
                "private_test_permit_denied",
            )
            require(
                intent not in s["intents"] or s["intents"][intent]["outcome"] == "registered",
                "private_test_intent_consumed",
            )
            s["grant"] = dict(
                intent=intent,
                participant=participant,
                expires_at=min(s["deadline"], int(time() * 1000) + 120000),
            )

        return self._change(mutate)

    def advance(self, prior, head, sequence, entry):
        return self.runtime_command(
            "advance", prior=prior, head=head, sequence=sequence, entry=entry
        )

    def runtime_command(self, action, **args):
        def mutate(s):
            require(
                s["boot"] == self.boot_id and s["epoch"] == self.epoch,
                "private_test_boot_superseded",
            )
            if action == "advance":
                require(
                    s["head"] == args["prior"] and args["sequence"] == s["sequence"] + 1,
                    "private_test_anchor_conflict",
                )
                s.update(head=args["head"], sequence=args["sequence"])
                entry = args["entry"]
                if entry["kind"] in ("pause", "boot"):
                    s.update(paused=True, enabled=False, grant=None)
                if entry["kind"] == "revoke":
                    p = entry["participant_hash"]
                    if p not in s["revoked"]:
                        s["revoked"].append(p)
                    s.update(paused=True, enabled=False, grant=None)
                return
            identity = args["intent"]
            intent = s["intents"].get(identity)
            if action in ("register", "consume"):
                grant = s["grant"]
                require(
                    s["enabled"]
                    and not s["paused"]
                    and not s["killed"]
                    and s["head"] == args["head"]
                    and grant
                    and grant["intent"] == identity
                    and grant["participant"] == args["participant"]
                    and self.permits_participant(s, args["participant"])
                    and grant["expires_at"] > time() * 1000,
                    "private_test_permission_expired",
                )
            if action == "register":
                require(len(s["intents"]) < 20 or intent, "private_test_cap")
                require(
                    not intent
                    or (
                        intent["outcome"] == "registered"
                        and intent["key"] == args["key"]
                        and intent["digest"] == args["digest"]
                        and intent["participant"] == args["participant"]
                    ),
                    "private_test_conflict",
                )
                require(
                    not any(
                        k != identity and v["key"] == args["key"] for k, v in s["intents"].items()
                    ),
                    "private_test_key_collision",
                )
                s["intents"][identity] = intent or dict(
                    key=args["key"],
                    digest=args["digest"],
                    participant=args["participant"],
                    outcome="registered",
                    token=None,
                    acceptance=None,
                )
            elif action == "consume":
                require(
                    intent
                    and intent["outcome"] == "registered"
                    and (intent["key"], intent["digest"]) == (args["key"], args["digest"]),
                    "private_test_already_consumed",
                )
                intent.update(
                    outcome="unknown",
                    token=args["token"],
                    boot=self.boot_id,
                    epoch=self.epoch,
                    expires_at=s["grant"]["expires_at"],
                    consumed_at=int(time() * 1000),
                )
                s["grant"] = None
            elif action == "check_submission":
                require(
                    s["enabled"]
                    and not s["paused"]
                    and not s["killed"]
                    and intent
                    and intent["outcome"] == "unknown"
                    and intent["boot"] == self.boot_id
                    and intent["epoch"] == self.epoch
                    and intent["expires_at"] > time() * 1000
                    and s["head"] == args["head"]
                    and (intent["token"], intent["digest"], intent["participant"])
                    == (args["token"], args["digest"], args["participant"])
                    and intent["participant"] not in s["revoked"],
                    "private_test_submission_denied",
                )
                self.submission_valid_until = (
                    monotonic() + (intent["expires_at"] / 1000 - time()) - 0.05
                )
            elif action == "outcome":
                require(
                    intent
                    and intent["outcome"] == "unknown"
                    and intent["boot"] == self.boot_id
                    and intent["epoch"] == self.epoch
                    and (intent["token"], intent["digest"]) == (args["token"], args["digest"])
                    and args["outcome"] == "accepted"
                    and len(args["acceptance"]) == 64,
                    "private_test_outcome_denied",
                )
                require(
                    not any(
                        k != identity and v["acceptance"] == args["acceptance"]
                        for k, v in s["intents"].items()
                    ),
                    "private_test_receipt_collision",
                )
                intent.update(
                    outcome="accepted",
                    acceptance=args["acceptance"],
                    accepted_at=int(time() * 1000),
                )
            else:
                raise AuthorityClosed("private_test_action_denied")

        return self._change(mutate)


class PrivateTestStore(CloudflareWahaStore):
    def generation_channel_is_available(self, **kwargs):
        return self.authority.active(
            self.authority.current()
        ) and super().generation_channel_is_available(**kwargs)

    def claim_next_delivery(self, **kwargs):
        if kwargs.get("provider") != "waha":
            return None
        with self.journal.lock:
            try:
                state = self.authority.current()
                if self.journal.paused or not self.authority.active(state):
                    return None
                with self._connect() as c:
                    rows = c.execute(
                        "SELECT i.provider_message_id,d.provider_channel_id,d.recipient_address "
                        "FROM outbound_deliveries d JOIN messages o ON o.id=d.outbound_message_id "
                        "JOIN messages i ON i.id=o.in_reply_to_message_id "
                        "WHERE d.provider='waha' AND d.state='pending' ORDER BY d.id"
                    ).fetchall()
                row = next(
                    (
                        r
                        for r in rows
                        if self.authority.permits_participant(
                            state, self.participant_identity(r[2])
                        )
                    ),
                    None,
                )
                if row is None:
                    return None
                self.authority.permit(
                    self.logical_identity(row[0], row[1]),
                    self.participant_identity(row[2]),
                    self.journal.head,
                )
                return super().claim_next_delivery(**kwargs)
            except AuthorityClosed:
                return None

    def egress_status(self):
        state = self.authority.current()
        enabled = not self.journal.paused and self.authority.active(state)
        return dict(
            egress=enabled,
            egress_blockers=[] if enabled else ["private_test_paused_or_exhausted"],
            authority_epoch=state["epoch"],
            mode="temporary_private_test",
            audience=state.get("audience", "allowlist"),
            saas_egress_blockers=["AUD-01", "AR-02"],
            test_expires_at=state["deadline"],
            test_intents=len(state["intents"]),
            test_limit=20,
            joint_rollback_protected=False,
        )


def create_waha_private_test_app():
    settings = WahaSettings(_env_file=".env.b1")
    cfg_path = Path("/authority/runtime.json")
    require(
        cfg_path.is_file() and not cfg_path.stat().st_mode & 0o077,
        "private_test_configuration_required",
    )
    cfg = json.loads(cfg_path.read_text())
    authority = LocalTestAuthority(
        Path("/authority/ledger.jsonl"), key=settings.waha_journal_key, scope=cfg["scope"]
    )
    require(
        authority.read().get("audience", "allowlist") == settings.waha_audience,
        "authority_audience_mismatch",
    )
    parts = {}

    def pipeline(s):
        def journal(*args, **kwargs):
            return AnchoredWahaJournal(*args, authority=authority, **kwargs)

        return build_waha_pipeline(s, journal_factory=journal, store_factory=PrivateTestStore)

    def outbound(adapter, journal, store, api):
        parts.update(adapter=adapter, journal=journal, store=store, api=api)
        return OutboundDeliveryExecutor(
            store=store,
            sender=AuthorizedWahaSender(store, api, adapter),
            request_timeout_seconds=5,
            poll_interval_seconds=1,
            concurrency=1,
            provider="waha",
            maximum_attempts=1,
        )

    app = create_waha_app(settings, pipeline_builder=pipeline, outbound_factory=outbound)

    @app.post("/ops/waha/private-test/start")
    def activate(request: Request):
        if not hmac.compare_digest(
            request.headers.get("authorization", ""), "Bearer " + settings.waha_operator_token
        ):
            raise HTTPException(403, "operator_authentication")
        with parts["journal"].lock:
            require(
                not parts["journal"].paused
                and (parts["adapter"].all_direct or len(parts["adapter"].participants) == 1),
                "private_test_resume_required",
            )
            info = parts["api"].session_info()
            require(
                info.get("status") == "WORKING"
                and parts["adapter"].identity_aliases.get((info.get("me") or {}).get("id"))
                == parts["adapter"].secondary,
                "private_test_secondary_unverified",
            )
            authority.activate()
        parts["store"].egress_status()
        return {
            "active": True,
            "scope": "temporary_private_test",
            "audience": settings.waha_audience,
            "max_replies": 20,
            "joint_rollback_protected": False,
            "saas_gates_closed": False,
        }

    return app
