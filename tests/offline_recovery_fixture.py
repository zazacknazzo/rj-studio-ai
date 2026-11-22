"""SQLite stand-ins for separately operated services. Synthetic tests ONLY."""

import hashlib
import json
import secrets
import sqlite3
from dataclasses import asdict, replace
from pathlib import Path

from rj_studio_ai.offline_recovery import AuthorityReply, AuthorityState, InventoryItem

RESOURCE = "synthetic-org/profile/number"


def decode(value):
    data = json.loads(value)
    data["inventory"] = tuple(InventoryItem(**item) for item in data["inventory"])
    return AuthorityState(**data)


class SQLiteWitness:
    def __init__(self, path: Path, genesis: AuthorityState):
        self.path = path
        self.available = True
        self.fail_next = False
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE witness(resource PRIMARY KEY,epoch,revision,digest,served_at)")
            db.execute(
                "INSERT INTO witness VALUES(?,?,?,?,?)",
                (genesis.resource, genesis.epoch, genesis.revision, genesis.digest(), 0),
            )

    def observe(self, resource, epoch, revision, digest, served_at):
        if not self.available or self.fail_next:
            self.fail_next = False
            raise OSError("synthetic_witness_unavailable")
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT epoch,revision,digest,served_at FROM witness WHERE resource=?", (resource,)
            ).fetchone()
            if row is None or epoch < row[0] or revision < row[1] or served_at < row[3]:
                raise ValueError("witness_regression")
            if revision == row[1] and (epoch, digest) != (row[0], row[2]):
                raise ValueError("witness_equivocation")
            db.execute(
                "UPDATE witness SET epoch=?,revision=?,digest=?,served_at=? WHERE resource=?",
                (epoch, revision, digest, served_at, resource),
            )


class SQLiteAuthority:
    def __init__(self, path: Path):
        self.path = path
        self.available = True
        self.stale_reply = None
        self.witness = None
        self.fail_commit = False
        self.now = 1_795_392_000  # synthetic clock, not commercial evidence
        self.tokens = {
            role: secrets.token_urlsafe(32)
            for role in ("application", "recoverer", "approver", "verifier", "security")
        }
        state = AuthorityState(
            RESOURCE,
            0,
            0,
            "",
            "",
            (),
            False,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            "0" * 64,
        )
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE state(resource PRIMARY KEY,body NOT NULL)")
            db.execute("INSERT INTO state VALUES(?,?)", (RESOURCE, json.dumps(asdict(state))))
            db.execute("CREATE TABLE actors(token_hash PRIMARY KEY,actor,role,resource,enabled)")
            for role, token in self.tokens.items():
                db.execute(
                    "INSERT INTO actors VALUES(?,?,?,?,1)",
                    (hashlib.sha256(token.encode()).hexdigest(), role, role, RESOURCE),
                )
            db.execute("CREATE TABLE audit(sequence INTEGER PRIMARY KEY,action,actor,result,chain)")
            for action in ("UPDATE", "DELETE"):
                db.execute(
                    f"CREATE TRIGGER audit_no_{action.lower()} BEFORE {action} ON audit "
                    "BEGIN SELECT RAISE(ABORT,'audit_retained'); END"
                )
            db.execute(
                "CREATE TRIGGER audit_no_replace BEFORE INSERT ON audit "
                "WHEN EXISTS(SELECT 1 FROM audit WHERE sequence=NEW.sequence) "
                "BEGIN SELECT RAISE(ABORT,'audit_retained'); END"
            )
            db.execute("CREATE TABLE reconciliation_proofs(ref PRIMARY KEY,intent,outcome,epoch)")

    def state(self):
        with sqlite3.connect(self.path) as db:
            return decode(
                db.execute("SELECT body FROM state WHERE resource=?", (RESOURCE,)).fetchone()[0]
            )

    def _actor(self, db, credential, resource, roles):
        row = db.execute(
            "SELECT actor,role,resource,enabled FROM actors WHERE token_hash=?",
            (hashlib.sha256(credential.encode()).hexdigest(),),
        ).fetchone()
        if row is None or not row[3] or row[2] != resource or row[1] not in roles:
            raise PermissionError("access_denied")
        return row[0]

    def read(self, resource, challenge, credential):
        if not self.available:
            raise OSError("authority_unavailable")
        with sqlite3.connect(self.path) as db:
            self._actor(db, credential, resource, {"application"})
            state = decode(
                db.execute("SELECT body FROM state WHERE resource=?", (resource,)).fetchone()[0]
            )
        if self.stale_reply is not None:
            return self.stale_reply
        return AuthorityReply(challenge, state, self.now)

    def _change(self, resource, challenge, credential, expected_revision, roles, action, mutate):
        if not self.available:
            raise OSError("authority_unavailable")
        failure = None
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            state = decode(
                db.execute("SELECT body FROM state WHERE resource=?", (resource,)).fetchone()[0]
            )
            actor = "unauthenticated"
            result = "allowed"
            try:
                actor = self._actor(db, credential, resource, roles)
                if state.revision != expected_revision:
                    raise ValueError("revision_conflict")
                state = mutate(db, state, actor)
            except (ValueError, PermissionError) as error:
                failure, result = error, "denied"
            revision = state.revision + 1
            chain = hashlib.sha256(
                json.dumps([state.audit_head, revision, action, actor, result]).encode()
            ).hexdigest()
            state = replace(state, revision=revision, audit_head=chain)
            db.execute(
                "INSERT INTO audit VALUES(?,?,?,?,?)", (revision, action, actor, result, chain)
            )
            db.execute(
                "UPDATE state SET body=? WHERE resource=?", (json.dumps(asdict(state)), resource)
            )
            if self.witness is not None:
                self.witness.observe(
                    resource, state.epoch, state.revision, state.digest(), self.now
                )
            if self.fail_commit:
                self.fail_commit = False
                raise OSError("synthetic_crash_after_witness_before_authority_commit")
        if failure:
            raise failure
        return AuthorityReply(challenge, state, self.now)

    def begin(
        self,
        resource,
        challenge,
        credential,
        *,
        expected_revision,
        session_id,
        snapshot_digest,
        inventory,
    ):
        def mutate(db, state, actor):
            merged = {item.intent_id: item for item in state.inventory}
            for item in inventory:
                if not item.submission_key:
                    raise ValueError("missing_stable_key")
                old = merged.get(item.intent_id)
                if old and (
                    old.submission_key != item.submission_key
                    or (
                        old.request_digest
                        and item.request_digest
                        and old.request_digest != item.request_digest
                    )
                ):
                    raise ValueError("inventory_identity_conflict")
                if any(
                    i.submission_key == item.submission_key and i.intent_id != item.intent_id
                    for i in merged.values()
                ):
                    raise ValueError("submission_key_reuse")
                if old is None:
                    merged[item.intent_id] = replace(
                        item,
                        outcome="conflict" if item.outcome == "conflict" else "unknown",
                        evidence_ref=None,
                    )
                elif item.outcome == "conflict":
                    merged[item.intent_id] = replace(old, outcome="conflict", evidence_ref=None)
            return replace(
                state,
                epoch=state.epoch + 1,
                session_id=session_id,
                snapshot_digest=snapshot_digest,
                inventory=tuple(sorted(merged.values(), key=lambda item: item.intent_id)),
                inventory_complete=False,
                binding_ref=None,
                sync_ref=None,
                consent_ref=None,
                window_ref=None,
                evidence_epoch=None,
                evidence_issued_at=None,
                evidence_expires_at=None,
                recovered_by=actor,
                released_by=None,
                released=False,
            )

        return self._change(
            resource, challenge, credential, expected_revision, {"recoverer"}, "begin", mutate
        )

    def seed_current_proofs(self, credential, *, complete=True, lifetime=60, missing=None):
        state = self.state()

        def mutate(db, current, actor):
            values = dict(
                binding_ref="synthetic-binding",
                sync_ref="synthetic-sync",
                consent_ref="synthetic-service-consent",
                window_ref="synthetic-window",
            )
            if missing:
                values[missing] = None
            return replace(
                current,
                inventory_complete=complete,
                evidence_epoch=current.epoch,
                evidence_issued_at=self.now,
                evidence_expires_at=self.now + lifetime,
                released=False,
                released_by=None,
                **values,
            )

        return self._change(
            RESOURCE,
            secrets.token_hex(),
            credential,
            state.revision,
            {"verifier"},
            "verify_proofs",
            mutate,
        )

    def release(self, resource, challenge, credential, *, expected_revision, session_id):
        def mutate(db, state, actor):
            if (
                state.session_id != session_id
                or actor == state.recovered_by
                or not state.inventory_complete
                or state.evidence_epoch != state.epoch
                or not all((state.binding_ref, state.sync_ref, state.consent_ref, state.window_ref))
                or state.evidence_issued_at is None
                or state.evidence_expires_at is None
                or not state.evidence_issued_at <= self.now < state.evidence_expires_at
                or any(
                    i.outcome not in {"accepted", "not_submitted"} or not i.evidence_ref
                    for i in state.inventory
                )
            ):
                raise ValueError("release_unproven")
            return replace(state, released=True, released_by=actor)

        return self._change(
            resource, challenge, credential, expected_revision, {"approver"}, "release", mutate
        )

    def revoke(self, resource, challenge, credential, *, expected_revision):
        return self._change(
            resource,
            challenge,
            credential,
            expected_revision,
            {"security"},
            "revoke",
            lambda db, state, actor: replace(state, released=False, released_by=None),
        )

    def approve_reconciliation(self, credential, *, intent_id, outcome):
        state = self.state()
        ref = "synthetic-proof-" + secrets.token_hex(12)

        def mutate(db, current, actor):
            db.execute(
                "INSERT INTO reconciliation_proofs VALUES(?,?,?,?)",
                (ref, intent_id, outcome, current.epoch),
            )
            return replace(current, released=False, released_by=None)

        self._change(
            RESOURCE,
            secrets.token_hex(),
            credential,
            state.revision,
            {"verifier"},
            "verify_reconciliation",
            mutate,
        )
        return ref

    def reconcile(
        self,
        resource,
        challenge,
        credential,
        *,
        expected_revision,
        session_id,
        intent_id,
        outcome,
        evidence_ref,
    ):
        def mutate(db, state, actor):
            proof = db.execute(
                "SELECT intent,outcome,epoch FROM reconciliation_proofs WHERE ref=?",
                (evidence_ref,),
            ).fetchone()
            if state.session_id != session_id or proof != (intent_id, outcome, state.epoch):
                raise ValueError("reconciliation_unproven")
            if outcome not in {"accepted", "not_submitted"}:
                raise ValueError("reconciliation_not_retryable")
            if not any(
                i.intent_id == intent_id and i.outcome == "unknown" for i in state.inventory
            ):
                raise ValueError("intent_not_unknown")
            return replace(
                state,
                inventory=tuple(
                    replace(i, outcome=outcome, evidence_ref=evidence_ref)
                    if i.intent_id == intent_id
                    else i
                    for i in state.inventory
                ),
                released=False,
                released_by=None,
            )

        return self._change(
            resource, challenge, credential, expected_revision, {"recoverer"}, "reconcile", mutate
        )

    def reserve(self, resource, challenge, credential, *, expected_revision, session_id, item):
        def mutate(db, state, actor):
            if (
                not state.released
                or state.session_id != session_id
                or not state.inventory_complete
                or state.evidence_epoch != state.epoch
                or not all((state.binding_ref, state.sync_ref, state.consent_ref, state.window_ref))
                or state.evidence_issued_at is None
                or state.evidence_expires_at is None
                or not state.evidence_issued_at <= self.now < state.evidence_expires_at
                or any(
                    i.outcome not in {"accepted", "not_submitted"} or not i.evidence_ref
                    for i in state.inventory
                )
            ):
                raise ValueError("quarantined")
            if any(
                i.intent_id == item.intent_id or i.submission_key == item.submission_key
                for i in state.inventory
            ):
                raise ValueError("old_work_or_key_reuse")
            if not item.submission_key or not item.request_digest:
                raise ValueError("request_unbound")
            return replace(
                state,
                inventory=(*state.inventory, replace(item, outcome="unknown", evidence_ref=None)),
                released=False,
                released_by=None,
            )

        return self._change(
            resource, challenge, credential, expected_revision, {"application"}, "reserve", mutate
        )

    def revoke_access(self, credential, target):
        state = self.state()

        def mutate(db, current, actor):
            db.execute(
                "UPDATE actors SET enabled=0 WHERE token_hash=?",
                (hashlib.sha256(target.encode()).hexdigest(),),
            )
            return replace(current, released=False, released_by=None)

        return self._change(
            RESOURCE,
            secrets.token_hex(),
            credential,
            state.revision,
            {"security"},
            "revoke_access",
            mutate,
        )
