"""Local B1 integrity/budget fences. These do NOT close AUD-01/AR-02."""

import fcntl
import hashlib
import hmac
import json
import os
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from rj_studio_ai.generation import GenerationFailure
from rj_studio_ai.persistence import PersistenceUnavailable, SqliteConversationStore


class WahaSafetyError(PersistenceUnavailable):
    pass


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _atomic_private(path, data):
    temporary = path.with_suffix(".pending")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as file:
        file.write(data)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


class WahaSafetyJournal:
    """MAC chain plus separate head; loss/partial commit/one-sided restore deny work.

    The two directories are still owned by the same host operator. Simultaneous
    rollback is NOT detectable; no production or private egress authority is minted.
    One process holds an OS lock for its lifetime; all mutations are serialized.
    """

    def __init__(self, directory: Path, witness: Path, *, key: str, scope: dict):
        if len(key) < 32 or directory.resolve() == witness.parent.resolve():
            raise ValueError("invalid_safety_roots")
        self.lock = RLock()
        self.directory, self.witness = directory, witness
        self.key = key.encode()
        for parent in (directory, witness.parent):
            parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(parent, 0o700)
        self.path = directory / "safety.jsonl"
        self.lockfile = (directory / "process.lock").open("a+")
        os.chmod(directory / "process.lock", 0o600)
        try:
            fcntl.flock(self.lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.path.exists() != witness.exists():
                raise WahaSafetyError("safety_root_missing")
            self.entries = []
            self.head = "0" * 64
            self.scope = hashlib.sha256(_encoded(scope)).hexdigest()
            if self.path.exists():
                self._read()
                if not self.entries or self.entries[0] != {"kind": "scope", "digest": self.scope}:
                    raise WahaSafetyError("safety_scope_changed")
            else:
                self.append({"kind": "scope", "digest": self.scope})
            self._state()
        except BaseException:
            self.close()
            raise

    def close(self):
        self.lockfile.close()

    def _read(self):
        entries = []
        head = "0" * 64
        try:
            for number, line in enumerate(self.path.read_bytes().splitlines(), 1):
                record = json.loads(line)
                unsigned = {k: record[k] for k in ("sequence", "prior", "entry")}
                mac = hmac.new(self.key, _encoded(unsigned), hashlib.sha256).hexdigest()
                if (
                    record["sequence"] != number
                    or record["prior"] != head
                    or not hmac.compare_digest(record["mac"], mac)
                ):
                    raise ValueError()
                head = mac
                entries.append(record["entry"])
            witness = json.loads(self.witness.read_bytes())
            if witness != {"sequence": len(entries), "head": head}:
                raise ValueError()
        except (ValueError, KeyError, TypeError, OSError):
            raise WahaSafetyError("safety_integrity_failed") from None
        if len(entries) < len(self.entries) or (
            len(entries) == len(self.entries) and self.entries and head != self.head
        ):
            raise WahaSafetyError("safety_live_rollback")
        self.entries, self.head = entries, head

    def append(self, entry):
        with self.lock:
            if self.entries:
                self._read()
            unsigned = {"sequence": len(self.entries) + 1, "prior": self.head, "entry": entry}
            mac = hmac.new(self.key, _encoded(unsigned), hashlib.sha256).hexdigest()
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "ab") as file:
                file.write(_encoded({**unsigned, "mac": mac}) + b"\n")
                file.flush()
                os.fsync(file.fileno())
            _atomic_private(self.witness, _encoded({"sequence": unsigned["sequence"], "head": mac}))
            self.entries.append(entry)
            self.head = mac

    def _state(self):
        self.paused = True
        self.revoked = set()
        self.reserved_tokens = 0
        self.reserved_microusd = 0
        self.calls = 0
        self.unresolved = False
        self.db_digest = None
        self.prepared = False
        for entry in self.entries:
            kind = entry["kind"]
            if kind in {"pause", "boot"}:
                self.paused = True
            elif kind == "resume":
                self.paused = False
            elif kind == "revoke":
                self.revoked.add(entry["participant_hash"])
            elif kind == "reserve":
                if self.unresolved:
                    raise WahaSafetyError("safety_invalid_reservation")
                self.calls += 1
                self.reserved_tokens += entry["tokens"]
                self.reserved_microusd += entry["microusd"]
                self.unresolved = True
            elif kind == "settle":
                if not self.unresolved:
                    raise WahaSafetyError("safety_invalid_settlement")
                self.unresolved = not entry["known"]
            elif kind == "prepare":
                if self.prepared:
                    raise WahaSafetyError("safety_incomplete_commit")
                self.prepared = True
            elif kind == "checkpoint":
                self.db_digest = entry["digest"]
                self.prepared = False

    def refresh(self):
        with self.lock:
            self._read()
            self._state()
            if self.prepared:
                raise WahaSafetyError("safety_incomplete_commit")

    def change(self, action, participant=None):
        with self.lock:
            self.refresh()
            if action not in {"pause", "resume", "boot", "revoke"}:
                raise ValueError("invalid_safety_action")
            entry = {"kind": action}
            if action == "revoke":
                if participant is None:
                    raise ValueError("participant_required")
                entry["participant_hash"] = hashlib.sha256(participant.encode()).hexdigest()
            self.append(entry)
            self._state()

    def permits_generation(self, participant):
        with self.lock:
            self.refresh()
            return (
                not self.paused
                and not self.unresolved
                and hashlib.sha256(participant.encode()).hexdigest() not in self.revoked
            )

    def reserve(self, *, input_tokens, output_tokens):
        with self.lock:
            self.refresh()
            # Versioned project-approved 2026-10-02 rates, conservative cache-write
            # price for every input token. This is an estimate, not current billing.
            tokens = input_tokens + output_tokens
            microusd = (input_tokens * 5 + 1) // 2 + output_tokens * 10
            if (
                self.paused
                or self.unresolved
                or self.calls >= 20
                or self.reserved_tokens + tokens > 500_000
                or self.reserved_microusd + microusd > 1_000_000
            ):
                raise GenerationFailure("waha_budget_or_pause")
            self.append({"kind": "reserve", "tokens": tokens, "microusd": microusd})
            self._state()

    def settle(self, *, known):
        with self.lock:
            self.append({"kind": "settle", "known": bool(known)})
            self._state()


def _database_digest(connection):
    digest = hashlib.sha256()
    for line in connection.iterdump():
        digest.update(line.encode())
        digest.update(b"\n")
    return digest.hexdigest()


class WahaConversationStore(SqliteConversationStore):
    """Canonical store with local anti-tamper sealing and immutable egress quarantine."""

    def __init__(self, path, *, journal):
        super().__init__(path, telnyx_egress_quarantined=True)
        self.journal = journal
        self._initializing = False

    def initialize(self):
        with self.journal.lock:
            self.journal.refresh()
            if self.journal.db_digest is None and self._database_path.exists():
                raise WahaSafetyError("unsealed_existing_database")
            if self.journal.db_digest is not None:
                with super()._connect() as c:
                    if _database_digest(c) != self.journal.db_digest:
                        raise WahaSafetyError("database_restore_or_tamper")
            self._initializing = True
            try:
                super().initialize()
            finally:
                self._initializing = False
            with super()._connect() as c:
                digest = _database_digest(c)
            self.journal.append({"kind": "checkpoint", "digest": digest})
            self.journal._state()
            self.journal.change("boot")

    @contextmanager
    def _connect(self, timeout_seconds=None):
        if self._initializing:
            with super()._connect(timeout_seconds) as c:
                yield c
            return
        with self.journal.lock:
            self.journal.refresh()
            with super()._connect(timeout_seconds) as c:
                before = _database_digest(c)
                if self.journal.db_digest != before:
                    raise WahaSafetyError("database_restore_or_tamper")
                yield c
                after = _database_digest(c)
                if before != after:
                    self.journal.append({"kind": "prepare", "digest": after})
            if before != after:
                self.journal.append({"kind": "checkpoint", "digest": after})
                self.journal._state()

    def generation_channel_is_available(self, *, inbound_message_id, lock_timeout=None):
        with self._connect(lock_timeout) as c:
            row = c.execute(
                "SELECT customer_address FROM conversations JOIN messages "
                "ON messages.conversation_id=conversations.id WHERE messages.id=?",
                (inbound_message_id,),
            ).fetchone()
        return (
            row is not None
            and self.journal.permits_generation(row[0])
            and super().generation_channel_is_available(
                inbound_message_id=inbound_message_id, lock_timeout=lock_timeout
            )
        )

    def authorize_delivery_submission(self, **kwargs):
        # Never delegate to the permissive generic-store path for WAHA.
        # No setting/CLI/operator action can turn this into authorization.
        return False

    def authorize_legacy_reply(self, **kwargs):
        return False

    @staticmethod
    def authorize_waha_http(message):
        del message
        return False
