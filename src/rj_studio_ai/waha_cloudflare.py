"""Concrete independently witnessed WAHA egress; B1's closed store stays closed."""

import hashlib
import hmac
import json
import os
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic, time
from urllib.parse import quote
from uuid import uuid4

from rj_studio_ai.delivery import OutboundDeliveryExecutor
from rj_studio_ai.providers.base import (
    OutboundMessageSender,
    OutboundOutcomeUnknown,
    ProviderAcceptance,
)
from rj_studio_ai.waha_authority import (
    AuthorityClosed,
    AuthorityConfig,
    CloudflareAuthority,
    encoded,
)
from rj_studio_ai.waha_safety import WahaConversationStore, WahaSafetyJournal


def prepare_waha(message):
    return json.dumps(
        {
            "session": "default",
            "chatId": message.recipient_address,
            "text": message.body,
            "linkPreview": False,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()


def observe_waha_acceptance(api, aliases, message, provider_id, *, submission):
    # A matching GET is not causal proof: an old/manual identical message can exist.
    # Only a provider ID already witnessed from this attempt's actual HTTP response
    # may finalize local state. A timeout without that receipt stays UNKNOWN.
    if (
        submission.get("outcome") != "accepted"
        or submission.get("acceptance") != hashlib.sha256(provider_id.encode()).hexdigest()
        or type(submission.get("consumed_at")) is not int
        or type(submission.get("accepted_at")) is not int
    ):
        raise AuthorityClosed("causal_acceptance_receipt_required")
    match = re.fullmatch(r"true_([0-9]{1,20}@(c\.us|lid))_[A-Za-z0-9_-]{1,128}", provider_id)
    if not match or aliases.get(match[1]) != message.recipient_address:
        raise AuthorityClosed("provider_evidence_recipient_invalid")
    info = api.session_info()
    if (
        info.get("status") != "WORKING"
        or aliases.get((info.get("me") or {}).get("id")) != message.sender_address
    ):
        raise AuthorityClosed("provider_evidence_session_invalid")
    response = api.request(
        "GET",
        "/api/default/chats/"
        + quote(match[1], safe="")
        + "/messages/"
        + quote(provider_id, safe="")
        + "?downloadMedia=false",
    )
    if response.status_code != 200:
        raise AuthorityClosed("provider_evidence_unavailable")
    raw = response.json()
    if (
        raw.get("id") != provider_id
        or raw.get("fromMe") is not True
        or raw.get("hasMedia") is not False
        or raw.get("body") != message.body
        or type(raw.get("timestamp")) is not int
        or not submission["consumed_at"] - 5000
        <= raw["timestamp"] * 1000
        <= submission["accepted_at"] + 5000
        or type(raw.get("ack")) is not int
        or raw["ack"] not in (1, 2, 3, 4)
        or (raw.get("to") is not None and aliases.get(raw["to"]) != message.recipient_address)
    ):
        raise AuthorityClosed("provider_evidence_unverified")
    return hashlib.sha256(
        encoded(
            {
                "provider_id": provider_id,
                "request_digest": hashlib.sha256(prepare_waha(message)).hexdigest(),
                "ack": raw["ack"],
                "timestamp": raw["timestamp"],
                "consumed_at": submission["consumed_at"],
                "accepted_at": submission["accepted_at"],
            }
        )
    ).hexdigest()


class AnchoredWahaJournal(WahaSafetyJournal):
    def __init__(self, *args, authority, **kwargs):
        self.authority = None
        self.failed = False
        super().__init__(*args, **kwargs)
        try:
            if self.scope != authority.config.scope:
                raise AuthorityClosed("authority_scope_mismatch")
            self.fault_path = self.directory / "authority-faults.jsonl"
            if self.fault_path.exists():
                state = authority.read()
                for line in self.fault_path.read_bytes().splitlines():
                    record = json.loads(line)
                    mac = record.pop("mac")
                    if (
                        not hmac.compare_digest(
                            mac, hmac.new(self.key, encoded(record), hashlib.sha256).hexdigest()
                        )
                        or state.get("last_repair_revision", 0) <= record["revision"]
                        or (
                            record.get("participant")
                            and record["participant"] not in state["revoked"]
                        )
                    ):
                        raise AuthorityClosed("anchoring_fault_requires_operator_recovery")
            authority.boot(self.head, len(self.entries))
            self.authority = authority
        except BaseException:
            self.close()
            raise

    def append(self, entry):
        with self.lock:
            if self.failed:
                raise AuthorityClosed("anchoring_fault_requires_operator_recovery")
            if self.authority is not None:
                self._read()
                unsigned = {"sequence": len(self.entries) + 1, "prior": self.head, "entry": entry}
                head = hmac.new(self.key, encoded(unsigned), hashlib.sha256).hexdigest()
                try:
                    self.authority.advance(self.head, head, unsigned["sequence"], entry)
                    super().append(entry)
                except BaseException:
                    self.failed = True
                    record = {
                        "revision": self.authority.state["revision"],
                        "kind": entry["kind"],
                        **(
                            {"participant": entry["participant_hash"]}
                            if entry["kind"] == "revoke"
                            else {}
                        ),
                    }
                    record["mac"] = hmac.new(self.key, encoded(record), hashlib.sha256).hexdigest()
                    fd = os.open(self.fault_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                    with os.fdopen(fd, "ab") as file:
                        file.write(encoded(record) + b"\n")
                        file.flush()
                        os.fsync(file.fileno())
                    raise
                return
            # Cloud witness/authority commit precedes the local journal fsync.
            # A partial write leaves roots inconsistent and requires reconciliation.
            super().append(entry)

    def refresh(self):
        if self.failed:
            raise AuthorityClosed("anchoring_fault_requires_operator_recovery")
        super().refresh()


class CloudflareWahaStore(WahaConversationStore):
    """Canonical store with strict local gates AND external one-shot authorization."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not isinstance(self.journal, AnchoredWahaJournal):
            raise ValueError("externally_anchored_journal_required")
        self.authority = self.journal.authority
        self._tickets = {}
        # Cover verification, provider deadline, external outcome and sealed local
        # finalization without refreshing a claim that may already have submitted.
        self._delivery_lease = timedelta(seconds=90)

    def logical_identity(self, inbound_id, channel):
        wire = encoded(["waha", channel, inbound_id, "service_response"])
        return hmac.new(self.journal.key, wire, hashlib.sha256).hexdigest()

    def participant_identity(self, address):
        return hashlib.sha256(address.encode()).hexdigest()

    def egress_status(self):
        try:
            self.journal.refresh()
            state = self.authority.current()
            permitted = (
                not self.journal.paused
                and not state["paused"]
                and not state["killed"]
                and bool(state["grant"])
                and state["grant"]["expires_at"] > time() * 1000
                and state["head"] == self.journal.head
            )
            return {
                "egress": permitted,
                "egress_blockers": [] if permitted else ["external_release_required"],
                "authority_epoch": state["epoch"],
            }
        except AuthorityClosed:
            return {"egress": False, "egress_blockers": ["external_authority_unverified"]}

    def claim_next_delivery(self, **kwargs):
        if kwargs.get("provider") != "waha":
            return None
        with self.journal.lock:
            try:
                state = self.authority.current()
            except AuthorityClosed:
                return None
            grant = state["grant"]
            if (
                self.journal.paused
                or state["paused"]
                or state["killed"]
                or not grant
                or grant["expires_at"] <= time() * 1000
            ):
                return None
            with self._connect() as connection:
                candidates = connection.execute(
                    "SELECT d.id,i.provider_message_id,d.provider_channel_id,d.recipient_address "
                    "FROM outbound_deliveries d JOIN messages o ON o.id=d.outbound_message_id "
                    "JOIN messages i ON i.id=o.in_reply_to_message_id "
                    "WHERE d.provider='waha' AND d.state IN ('pending','retryable')"
                ).fetchall()
            selected = next(
                (
                    row[0]
                    for row in candidates
                    if self.logical_identity(row[1], row[2]) == grant["intent"]
                    and self.participant_identity(row[3]) == grant["participant"]
                ),
                None,
            )
            if selected is None:
                return None
            kwargs["only_delivery_id"] = selected
            claim = super().claim_next_delivery(**kwargs)
            if claim is None:
                return None
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT i.provider_message_id FROM messages o "
                    "JOIN messages i ON i.id=o.in_reply_to_message_id WHERE o.id=?",
                    (claim.outbound_message_id,),
                ).fetchone()
                identity = self.logical_identity(row[0], claim.provider_channel_id)
                key = identity[:32]
                if claim.submission_key is not None and claim.submission_key != key:
                    raise AuthorityClosed("submission_key_conflict")
                connection.execute(
                    "UPDATE outbound_deliveries SET submission_key=? "
                    "WHERE id=? AND owner_token=? AND submission_key IS NULL",
                    (key, claim.delivery_id, claim.owner_token),
                )
            return replace(claim, submission_key=key)

    def _eligible(self, delivery_id, owner_token, message, *, marked):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT i.provider_message_id, d.provider_channel_id, d.recipient_address, "
                "d.submission_key, o.body, d.submission_started_at, d.lease_expires_at "
                "FROM outbound_deliveries d JOIN messages o ON o.id=d.outbound_message_id "
                "JOIN messages i ON i.id=o.in_reply_to_message_id "
                "JOIN message_processing p ON p.inbound_message_id=i.id "
                "WHERE d.id=? AND d.owner_token=? AND d.state='sending' AND d.provider='waha' "
                "AND d.lease_expires_at>? AND p.state='completed' AND d.status_conflict=0 "
                "AND NOT EXISTS (SELECT 1 FROM conversation_automation_controls c "
                "WHERE c.conversation_id=o.conversation_id AND "
                "(c.paused=1 OR c.revision!=p.automation_revision)) "
                "AND NOT EXISTS (SELECT 1 FROM outbound_deliveries conflict "
                "JOIN messages prior ON prior.id=conflict.outbound_message_id "
                "WHERE prior.conversation_id=o.conversation_id AND conflict.status_conflict=1) "
                "AND ((d.handoff_token IS NULL AND NOT EXISTS (SELECT 1 FROM "
                "conversation_handoffs h WHERE h.conversation_id=o.conversation_id "
                "AND h.active=1)) "
                "OR EXISTS (SELECT 1 FROM conversation_handoffs h WHERE "
                "h.conversation_id=o.conversation_id AND h.active=1 "
                "AND h.owner_token=d.handoff_token))",
                (delivery_id, owner_token, datetime.now(UTC).isoformat()),
            ).fetchone()
        if (
            not row
            or self.journal.paused
            or self.participant_identity(message.recipient_address) in self.journal.revoked
            or (row[5] is not None) != marked
            or (row[1], row[2], row[3], row[4])
            != (
                message.sender_address,
                message.recipient_address,
                message.submission_key,
                message.body,
            )
        ):
            raise AuthorityClosed("local_submission_not_eligible")
        return row

    def authorize_delivery_submission(self, *, delivery_id, owner_token, message=None, **kwargs):
        if message is None:
            return False
        with self.journal.lock:
            row = self._eligible(delivery_id, owner_token, message, marked=False)
            identity = self.logical_identity(row[0], row[1])
            wire = prepare_waha(message)
            request_digest = hashlib.sha256(wire).hexdigest()
            participant = self.participant_identity(row[2])
            args = {
                "intent": identity,
                "participant": participant,
                "digest": request_digest,
                "key": message.submission_key,
                "head": self.journal.head,
            }
            self.authority.runtime_command("register", **args)
            token = uuid4().hex
            self.authority.runtime_command("consume", token=token, **args)
            # A consumed external identity can never be registered again, even if
            # the local marker transaction or HTTP below fails or is restored.
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                timestamp = datetime.now(UTC).isoformat()
                updated = connection.execute(
                    "UPDATE outbound_deliveries SET submission_started_at=?, "
                    "first_submission_at=COALESCE(first_submission_at,?),payload_fingerprint=? "
                    "WHERE id=? AND owner_token=? AND state='sending' "
                    "AND submission_started_at IS NULL AND lease_expires_at>?",
                    (timestamp, timestamp, request_digest, delivery_id, owner_token, timestamp),
                ).rowcount
                marked = connection.execute(
                    "UPDATE delivery_attempts SET submission_started_at=? "
                    "WHERE outbound_delivery_id=? AND owner_token=? AND outcome='started' "
                    "AND submission_started_at IS NULL",
                    (timestamp, delivery_id, owner_token),
                ).rowcount
                if updated != 1 or marked != 1:
                    raise AuthorityClosed("local_submission_marker_lost")
            self._tickets[message.submission_key] = {
                "delivery_id": delivery_id,
                "owner_token": owner_token,
                "intent": identity,
                "participant": participant,
                "digest": request_digest,
                "token": token,
                "wire": wire,
            }
            return True

    def exchange(self, message, *, api, aliases, timeout_seconds):
        with self.journal.lock:
            ticket = self._tickets.pop(message.submission_key, None)
            if ticket is None or ticket["wire"] != prepare_waha(message):
                raise OutboundOutcomeUnknown("one_shot_submission_ticket_missing")
            try:
                row = self._eligible(
                    ticket["delivery_id"], ticket["owner_token"], message, marked=True
                )
                info = api.session_info()
                if (
                    info.get("status") != "WORKING"
                    or aliases.get((info.get("me") or {}).get("id")) != message.sender_address
                    or aliases.get(message.recipient_address) != message.recipient_address
                    or (datetime.fromisoformat(row[6]) - datetime.now(UTC)).total_seconds() < 40
                ):
                    raise AuthorityClosed("current_secondary_or_lease_unverified")
                self.authority.runtime_command(
                    "check_submission",
                    intent=ticket["intent"],
                    participant=ticket["participant"],
                    digest=ticket["digest"],
                    token=ticket["token"],
                    head=self.journal.head,
                )
                remaining = self.authority.submission_valid_until - monotonic()
                if remaining < timeout_seconds:
                    raise AuthorityClosed("submission_deadline_too_short")
                remaining_lease = (
                    datetime.fromisoformat(row[6]) - datetime.now(UTC)
                ).total_seconds()
                if remaining_lease < timeout_seconds + 20:
                    raise AuthorityClosed("submission_lease_too_short")
                result = api.request(
                    "POST",
                    "/api/sendText",
                    content=ticket["wire"],
                    timeout=min(timeout_seconds, remaining),
                )
                if result.status_code not in (200, 201):
                    raise ValueError()
                raw = result.json()
                raw_recipient = raw.get("to")
                provider_id = raw.get("id")
                # WEBJS Core returns whatsapp-web.js Message.id; normalized engines
                # return a string. Bind every nested component before accepting it.
                if isinstance(provider_id, dict):
                    nested = provider_id
                    if (
                        nested.get("fromMe") is not True
                        or not isinstance(nested.get("remote"), str)
                        or aliases.get(nested["remote"]) != message.recipient_address
                        or not isinstance(nested.get("id"), str)
                        or nested.get("_serialized")
                        != "true_" + nested["remote"] + "_" + nested["id"]
                    ):
                        raise ValueError()
                    provider_id = nested["_serialized"]
                if (
                    raw.get("fromMe") is not True
                    or aliases.get(raw_recipient) != message.recipient_address
                    or not isinstance(provider_id, str)
                    or not (
                        id_match := re.fullmatch(
                            r"true_([0-9]{1,20}@(c\.us|lid))_[A-Za-z0-9_-]{1,128}", provider_id
                        )
                    )
                    or aliases.get(id_match[1]) != message.recipient_address
                ):
                    raise ValueError()
                self.authority.runtime_command(
                    "outcome",
                    intent=ticket["intent"],
                    digest=ticket["digest"],
                    token=ticket["token"],
                    outcome="accepted",
                    acceptance=hashlib.sha256(provider_id.encode()).hexdigest(),
                )
                return ProviderAcceptance(provider_id)
            except Exception:
                # Includes failures after real provider acceptance; never resend.
                raise OutboundOutcomeUnknown("cloudflare_waha_outcome_unknown") from None

    def reconcile_provider_message(self, identity, provider_id, *, api, aliases):
        from rj_studio_ai.domain import OutboundMessage

        with self.journal.lock:
            state = self.authority.current()
            intent = state["intents"].get(identity)
            if (
                not intent
                or intent["outcome"] != "accepted"
                or intent["acceptance"] != hashlib.sha256(provider_id.encode()).hexdigest()
            ):
                raise AuthorityClosed("external_acceptance_unverified")
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT d.id,d.provider_channel_id,d.recipient_address,o.body,"
                    "i.provider_message_id,d.attempt_count FROM outbound_deliveries d "
                    "JOIN messages o ON o.id=d.outbound_message_id "
                    "JOIN messages i ON i.id=o.in_reply_to_message_id "
                    "WHERE d.provider='waha' AND d.state IN ('unknown','sending') "
                    "AND d.first_submission_at IS NOT NULL"
                ).fetchall()
            row = next((r for r in rows if self.logical_identity(r[4], r[1]) == identity), None)
            if row is None:
                raise AuthorityClosed("local_unknown_submission_not_found")
            message = OutboundMessage(row[1], row[2], row[3], submission_key=intent["key"])
            if hashlib.sha256(prepare_waha(message)).hexdigest() != intent["digest"]:
                raise AuthorityClosed("local_unknown_request_conflict")
            evidence = observe_waha_acceptance(
                api, aliases, message, provider_id, submission=intent
            )
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO waha_reconciliation_evidence(delivery_id,intent_id,"
                    "provider_message_id,request_digest,authority_revision,evidence_digest,"
                    "observed_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(delivery_id) DO NOTHING",
                    (
                        row[0],
                        identity,
                        provider_id,
                        intent["digest"],
                        state["revision"],
                        evidence,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                changed = connection.execute(
                    "UPDATE outbound_deliveries SET state='accepted',provider_message_id=?,"
                    "accepted_at=?,updated_at=?,safe_error_code=NULL,owner_token=NULL,"
                    "lease_expires_at=NULL WHERE id=? AND state IN ('unknown','sending')",
                    (
                        provider_id,
                        datetime.now(UTC).isoformat(),
                        datetime.now(UTC).isoformat(),
                        row[0],
                    ),
                ).rowcount
                if changed != 1:
                    raise AuthorityClosed("reconciliation_ownership_changed")
                changed = connection.execute(
                    "UPDATE delivery_attempts SET outcome='accepted',provider_message_id=?,"
                    "safe_error_code=NULL,completed_at=? WHERE outbound_delivery_id=? "
                    "AND attempt_number=? AND outcome IN ('unknown','started')",
                    (provider_id, datetime.now(UTC).isoformat(), row[0], row[5]),
                ).rowcount
                if changed != 1:
                    raise AuthorityClosed("reconciliation_attempt_missing")
            return True


class AuthorizedWahaSender(OutboundMessageSender):
    def __init__(self, store, api, adapter):
        if not isinstance(store, CloudflareWahaStore):
            raise ValueError("concrete_cloudflare_store_required")
        self.store, self.api, self.adapter = store, api, adapter

    def send(self, message, *, timeout_seconds):
        return self.store.exchange(
            message,
            api=self.api,
            aliases=self.adapter.reply_aliases(message.recipient_address),
            timeout_seconds=timeout_seconds,
        )


def create_waha_cloudflare_app():
    from rj_studio_ai.waha_live import WahaSettings, build_waha_pipeline, create_waha_app

    path = Path("/authority/runtime.json")
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise AuthorityClosed("private_runtime_authority_configuration_required")
    authority = CloudflareAuthority(AuthorityConfig(**json.loads(path.read_text())))

    def pipeline(settings):
        def journal(*args, **kwargs):
            return AnchoredWahaJournal(*args, authority=authority, **kwargs)

        return build_waha_pipeline(
            settings, journal_factory=journal, store_factory=CloudflareWahaStore
        )

    def outbound(adapter, journal, store, api):
        return OutboundDeliveryExecutor(
            store=store,
            sender=AuthorizedWahaSender(store, api, adapter),
            request_timeout_seconds=5,
            poll_interval_seconds=5,
            concurrency=1,
            provider="waha",
            maximum_attempts=1,
        )

    return create_waha_app(
        WahaSettings(_env_file=".env.b1"), pipeline_builder=pipeline, outbound_factory=outbound
    )
