"""Recovery protocol laboratory; never authorizes a transport or changes quarantine.

Authority and witness adapters MUST be independent of the application snapshot.
Only test adapters exist. No production factory, endpoint, worker or release CLI.
"""

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from rj_studio_ai.persistence import SqliteConversationStore


class RecoveryClosed(RuntimeError):
    """Finite diagnostic only; adapter failures must not disclose credentials."""


@dataclass(frozen=True, slots=True)
class InventoryItem:
    intent_id: str
    submission_key: str
    request_digest: str | None
    outcome: str = "unknown"
    evidence_ref: str | None = None


@dataclass(frozen=True, slots=True)
class AuthorityState:
    resource: str
    epoch: int
    revision: int
    session_id: str
    snapshot_digest: str
    inventory: tuple[InventoryItem, ...]
    inventory_complete: bool
    binding_ref: str | None
    sync_ref: str | None
    consent_ref: str | None
    window_ref: str | None
    evidence_epoch: int | None
    evidence_issued_at: int | None
    evidence_expires_at: int | None
    recovered_by: str | None
    released_by: str | None
    released: bool
    audit_head: str

    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class AuthorityReply:
    """Authenticated adapter reply, challenge-bound; not a bearer capability."""

    challenge: str
    state: AuthorityState
    served_at: int


class FreshnessAuthority(Protocol):
    """External linearizable, authenticated and independently retained contract.

    Every mutation advances revision, including access/evidence revocation.
    Reads verify authenticity and freshness against the unpredictable challenge.
    begin rotates epoch and revokes all previous releases; imports local inventory
    conservatively without replacing known keys or losing external-only intents.
    release checks current independently verified proofs and two distinct operators.
    reconcile never changes keys and requires authoritative scoped evidence.
    reserve records possible submission durably BEFORE any simulated exchange.
    All commands are CAS, authenticated/authorized, and append audited, including
    denied operations. No operational implementation is provided by this package.
    """

    def read(self, resource: str, challenge: str, credential: str) -> AuthorityReply: ...

    def begin(
        self,
        resource: str,
        challenge: str,
        credential: str,
        *,
        expected_revision: int,
        session_id: str,
        snapshot_digest: str,
        inventory: tuple[InventoryItem, ...],
    ) -> AuthorityReply: ...

    def release(
        self,
        resource: str,
        challenge: str,
        credential: str,
        *,
        expected_revision: int,
        session_id: str,
    ) -> AuthorityReply: ...

    def revoke(
        self,
        resource: str,
        challenge: str,
        credential: str,
        *,
        expected_revision: int,
    ) -> AuthorityReply: ...

    def reconcile(
        self,
        resource: str,
        challenge: str,
        credential: str,
        *,
        expected_revision: int,
        session_id: str,
        intent_id: str,
        outcome: str,
        evidence_ref: str,
    ) -> AuthorityReply: ...

    def reserve(
        self,
        resource: str,
        challenge: str,
        credential: str,
        *,
        expected_revision: int,
        session_id: str,
        item: InventoryItem,
    ) -> AuthorityReply: ...


class FreshnessWitness(Protocol):
    def observe(
        self, resource: str, epoch: int, revision: int, digest: str, served_at: int
    ) -> None:
        """Durable monotonic compare; reject regressions and same-revision changes."""


def intent_identity(provider: str, channel: str, inbound_id: str) -> str:
    """Stable logical identity independent of local row IDs or a replacement key."""
    return hashlib.sha256(
        json.dumps(
            [provider, channel, inbound_id, "service_response"], separators=(",", ":")
        ).encode()
    ).hexdigest()


def snapshot_inventory(path: Path) -> tuple[str, tuple[InventoryItem, ...]]:
    """Consistent SQLite read; retain only fingerprints/identities, never body text."""
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        connection.execute("BEGIN")
        digest = hashlib.sha256()
        for line in connection.iterdump():
            digest.update(line.encode())
            digest.update(b"\n")
        rows = connection.execute(
            "SELECT d.provider,d.provider_channel_id,i.provider_message_id,d.submission_key,"
            "r.request_mac,d.first_submission_at,d.state,d.status_conflict "
            "FROM outbound_deliveries d JOIN messages o ON o.id=d.outbound_message_id "
            "JOIN messages i ON i.id=o.in_reply_to_message_id "
            "LEFT JOIN telnyx_http_requests r ON r.submission_key=d.submission_key "
            "WHERE d.provider='telnyx' ORDER BY d.id"
        ).fetchall()
    inventory = tuple(
        InventoryItem(
            intent_identity(provider, channel, inbound_id),
            key or "",
            mac,
            "conflict" if conflict else "unknown",
        )
        for provider, channel, inbound_id, key, mac, _started, _state, conflict in rows
    )
    return digest.hexdigest(), inventory


class OfflineRecoverySession:
    """Fail-closed executable rehearsal. Even a release grants zero egress."""

    def __init__(
        self,
        store: SqliteConversationStore,
        authority: FreshnessAuthority,
        witness: FreshnessWitness,
        *,
        resource: str,
        application_credential: str,
    ) -> None:
        if store._telnyx_egress_quarantined is not True:
            raise ValueError("Recovery laboratory requires an explicitly quarantined store")
        self._store = store
        self._authority = authority
        self._witness = witness
        self._resource = resource
        self._application_credential = application_credential
        self._session_id = uuid4().hex
        self._epoch: int | None = None
        self._snapshot_digest: str | None = None
        self._closed = True
        self._served_at = 0

    def _accept(self, reply: AuthorityReply, challenge: str) -> AuthorityState:
        state = reply.state
        if (
            reply.challenge != challenge
            or state.resource != self._resource
            or type(state.epoch) is not int
            or type(state.revision) is not int
            or state.epoch < 0
            or state.revision < state.epoch
            or type(reply.served_at) is not int
            or reply.served_at < 0
        ):
            raise RecoveryClosed("authority_response_invalid")
        self._witness.observe(
            self._resource, state.epoch, state.revision, state.digest(), reply.served_at
        )
        self._served_at = reply.served_at
        return state

    def _read(self) -> AuthorityState:
        challenge = uuid4().hex
        return self._accept(
            self._authority.read(self._resource, challenge, self._application_credential), challenge
        )

    def begin(self, recovery_credential: str) -> AuthorityState:
        self._closed = True
        try:
            previous = self._read()
            digest, inventory = snapshot_inventory(self._store._database_path)
            challenge = uuid4().hex
            state = self._accept(
                self._authority.begin(
                    self._resource,
                    challenge,
                    recovery_credential,
                    expected_revision=previous.revision,
                    session_id=self._session_id,
                    snapshot_digest=digest,
                    inventory=inventory,
                ),
                challenge,
            )
            if (
                state.epoch <= previous.epoch
                or state.revision <= previous.revision
                or state.session_id != self._session_id
                or state.snapshot_digest != digest
                or state.released
            ):
                raise RecoveryClosed("begin_fence_invalid")
            self._epoch, self._snapshot_digest = state.epoch, digest
            self._closed = False
            return state
        except Exception:
            self._closed = True
            raise RecoveryClosed("recovery_begin_failed") from None

    def _current(self) -> AuthorityState:
        if self._closed or self._epoch is None:
            raise RecoveryClosed("quarantined")
        state = self._read()
        digest, _ = snapshot_inventory(self._store._database_path)
        if (
            state.epoch != self._epoch
            or state.session_id != self._session_id
            or state.snapshot_digest != digest
            or digest != self._snapshot_digest
        ):
            raise RecoveryClosed("session_or_snapshot_changed")
        return state

    def _command(self, action: str, credential: str, **kwargs) -> AuthorityState:
        try:
            current = self._current()
            challenge = uuid4().hex
            command = getattr(self._authority, action)
            arguments = dict(expected_revision=current.revision, **kwargs)
            if action != "revoke":
                arguments["session_id"] = self._session_id
            state = self._accept(
                command(self._resource, challenge, credential, **arguments), challenge
            )
            if state.revision <= current.revision or state.epoch != current.epoch:
                raise RecoveryClosed("command_fence_invalid")
            return state
        except Exception:
            self._closed = True
            raise RecoveryClosed("recovery_command_failed") from None

    def release(self, approval_credential: str) -> AuthorityState:
        return self._command("release", approval_credential)

    def revoke(self, security_credential: str) -> AuthorityState:
        return self._command("revoke", security_credential)

    def reconcile(
        self,
        recovery_credential: str,
        *,
        intent_id: str,
        outcome: str,
        evidence_ref: str,
    ) -> AuthorityState:
        if outcome not in {"accepted", "not_submitted"}:
            raise RecoveryClosed("reconciliation_outcome_invalid")
        return self._command(
            "reconcile",
            recovery_credential,
            intent_id=intent_id,
            outcome=outcome,
            evidence_ref=evidence_ref,
        )

    def reserve_simulated_submission(self, item: InventoryItem) -> AuthorityState:
        """Only records a possible attempt; no callback/transport can be supplied."""
        return self.record_possible_submission(item)

    def record_possible_submission(self, item: InventoryItem) -> AuthorityState:
        """Exercise the external write-ahead contract; zero HTTP or local authorization."""
        if not self.readiness()["simulation_ready"]:
            raise RecoveryClosed("quarantined")
        return self._command("reserve", self._application_credential, item=item)

    def readiness(self) -> dict:
        try:
            state = self._current()
            ready = (
                state.released
                and state.inventory_complete
                and state.evidence_epoch == state.epoch
                and state.evidence_issued_at is not None
                and state.evidence_expires_at is not None
                and state.evidence_issued_at <= self._served_at < state.evidence_expires_at
                and all((state.binding_ref, state.sync_ref, state.consent_ref, state.window_ref))
                and bool(state.recovered_by)
                and bool(state.released_by)
                and state.recovered_by != state.released_by
                and all(
                    item.outcome in {"accepted", "not_submitted"} and bool(item.evidence_ref)
                    for item in state.inventory
                )
            )
            return dict(
                simulation_ready=bool(ready),
                operational_egress=False,
                reason="simulation_released" if ready else "quarantined",
                epoch=state.epoch,
                blocked_intents=tuple(i.intent_id for i in state.inventory),
            )
        except Exception:
            self._closed = True
            return dict(
                simulation_ready=False,
                operational_egress=False,
                reason="quarantined",
                epoch=None,
                blocked_intents=(),
            )
