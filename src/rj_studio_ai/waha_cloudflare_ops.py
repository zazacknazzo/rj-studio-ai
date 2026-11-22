"""Cloudflare provisioning and operator actions; runtime never receives admin keys."""

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
from pathlib import Path
from time import time
from uuid import uuid4

import httpx
from nacl.signing import SigningKey, VerifyKey

from rj_studio_ai.domain import OutboundMessage
from rj_studio_ai.providers.waha import phone_chat
from rj_studio_ai.waha_authority import AuthorityConfig, CloudflareAuthority, encoded
from rj_studio_ai.waha_cli import api, config, operator_request
from rj_studio_ai.waha_cloudflare import observe_waha_acceptance, prepare_waha

PRIVATE = Path(".local/b3/cloudflare")


def private_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as file:
        json.dump(value, file, indent=2)
        file.flush()
        os.fsync(file.fileno())


def read_private(path):
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError("private_configuration_missing_or_not_0600")
    return json.loads(path.read_text())


def wrangler(*args):
    executable = Path("infra/waha-authority/node_modules/wrangler/bin/wrangler.js").resolve()
    environment = os.environ.copy()
    environment.update(WRANGLER_LOG="info", WRANGLER_SEND_METRICS="false")
    return subprocess.run(
        [shutil.which("node"), str(executable), *args],
        capture_output=True,
        text=True,
        env=environment,
        timeout=120,
        check=False,
    )


def signing_pair():
    key = SigningKey.generate()

    def b64(value):
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    return (
        json.dumps(
            {"kty": "OKP", "crv": "Ed25519", "d": b64(bytes(key)), "x": b64(bytes(key.verify_key))}
        ),
        bytes(key.verify_key).hex(),
    )


def current_scope(values):
    lines = Path(".local/b1/control/safety.jsonl").read_bytes().splitlines()
    prior = "0" * 64
    for index, line in enumerate(lines, 1):
        record = json.loads(line)
        unsigned = {k: record[k] for k in ("sequence", "prior", "entry")}
        mac = hmac.new(
            values["WAHA_JOURNAL_KEY"].encode(), encoded(unsigned), hashlib.sha256
        ).hexdigest()
        if (
            record["sequence"] != index
            or record["prior"] != prior
            or not hmac.compare_digest(record["mac"], mac)
        ):
            raise ValueError("local_journal_unverified")
        prior = mac
    witness = json.loads(Path(".local/b1/witness/head.json").read_text())
    if witness != {"head": prior, "sequence": len(lines)}:
        raise ValueError("local_journal_changing_retry_read")
    return json.loads(lines[0])["entry"]["digest"], prior, len(lines)


def prepare():
    if PRIVATE.exists():
        raise ValueError("private_deployment_already_prepared_do_not_overwrite")
    identity = wrangler("whoami", "--json")
    if identity.returncode:
        raise ValueError("cloudflare_login_required_run_wrangler_login_privately")
    accounts = json.loads(identity.stdout)["accounts"]
    if len(accounts) != 1:
        raise ValueError("exactly_one_primary_account_required_for_initial_preparation")
    account = accounts[0]["id"]
    values = config()
    scope, _, _ = current_scope(values)
    participants = [
        hashlib.sha256(phone_chat(p).encode()).hexdigest()
        for p in json.loads(values["WAHA_AUTHORIZED_PHONES"])
    ]
    authority_jwk, authority_public = signing_pair()
    witness_jwk, witness_public = signing_pair()
    witness_key = secrets.token_urlsafe(48)
    primary_name = "livia-waha-authority-b3"
    canary_name = "livia-waha-witness-canary-b3"
    common = {
        "main": str(Path("infra/waha-authority/src/worker.mjs").resolve()),
        "account_id": account,
        "compatibility_date": "2026-11-20",
        "workers_dev": True,
        "observability": {"enabled": False},
    }
    authority_vars = {
        "ROLE": "authority",
        "ACCOUNT_ID": account,
        "SCOPE": scope,
        "PARTICIPANTS": json.dumps(participants),
        "WITNESS_ACCOUNT_ID": account,
        "WITNESS_PUBLIC_KEY": witness_public,
        "WITNESS_URL": "https://not-configured.workers.dev/command",
    }
    for name, role, class_name, variables, secret_values, public_key in (
        (
            primary_name,
            "authority",
            "Authority",
            authority_vars,
            {
                "RUNTIME_KEY": secrets.token_urlsafe(48),
                "OPERATOR_KEY": secrets.token_urlsafe(48),
                "SIGNING_JWK": authority_jwk,
                "WITNESS_KEY": witness_key,
            },
            authority_public,
        ),
        (
            canary_name,
            "canary",
            "Witness",
            {"ROLE": "witness", "ACCOUNT_ID": account, "SCOPE": scope},
            {
                "AUTHORITY_KEY": witness_key,
                "OPERATOR_KEY": secrets.token_urlsafe(48),
                "SIGNING_JWK": witness_jwk,
            },
            witness_public,
        ),
    ):
        binding = "AUTHORITY" if role == "authority" else "WITNESS"
        document = {
            **common,
            "name": name,
            "vars": variables,
            "durable_objects": {"bindings": [{"name": binding, "class_name": class_name}]},
            "migrations": [{"tag": "v1", "new_sqlite_classes": [class_name]}],
        }
        private_write(PRIVATE / f"{role}.wrangler.json", document)
        private_write(PRIVATE / f"{role}.secrets.json", secret_values)
        private_write(
            PRIVATE / f"{role}.identity.json",
            {"account": account, "scope": scope, "public_key": public_key, "name": name},
        )
    print(
        json.dumps(
            {
                "prepared": True,
                "independent_administration": False,
                "runtime_configuration_created": False,
                "whatsapp_egress": False,
            }
        )
    )


def deploy(role):
    path = PRIVATE / f"{role}.wrangler.json"
    document = read_private(path)
    if (PRIVATE / f"{role}.deploy-log.json").exists() or (
        PRIVATE / f"{role}.endpoint.json"
    ).exists():
        raise ValueError("deployment_receipt_exists_reconcile_before_another_deploy")
    probe = wrangler("deployments", "list", "--config", str(path), "--json")
    if probe.returncode == 0:
        raise ValueError("remote_worker_exists_without_owned_deployment_receipt")
    if not re.search(r"code:\s*10007", probe.stderr):
        raise ValueError("remote_worker_absence_unverified")
    result = wrangler(
        "deploy", "--config", str(path), "--secrets-file", str(PRIVATE / f"{role}.secrets.json")
    )
    urls = re.findall(r"https://[a-zA-Z0-9.-]+\.workers\.dev", result.stdout + result.stderr)
    private_write(
        PRIVATE / f"{role}.deploy-log.json",
        {
            "output_digest": hashlib.sha256((result.stdout + result.stderr).encode()).hexdigest(),
            "exit_code": result.returncode,
            "url": urls[-1] if urls else None,
            "source_digest": hashlib.sha256(Path(document["main"]).read_bytes()).hexdigest(),
        },
    )
    if result.returncode:
        raise ValueError("cloudflare_deployment_failed_private_log_available")
    if not urls:
        # Query the account subdomain through the already authenticated CLI output
        # rather than guessing a personal or account identifier.
        raise ValueError("cloudflare_deployed_url_not_in_output_inspect_privately")
    private_write(
        PRIVATE / f"{role}.endpoint.json", {"url": urls[-1] + "/command", "name": document["name"]}
    )
    print(json.dumps({"deployed": True, "role": role, "whatsapp_egress": False}))


def raw_command(role, action, args, *, credential="operator", expected=None):
    identity = read_private(PRIVATE / f"{role}.identity.json")
    credentials = read_private(PRIVATE / f"{role}.secrets.json")
    endpoint = read_private(PRIVATE / f"{role}.endpoint.json")["url"]
    command = {
        "v": 1,
        "scope": identity["scope"],
        "nonce": uuid4().hex,
        "time": int(time() * 1000),
        "action": action,
        "args": args,
    }
    if expected is not None:
        command["expected"] = expected
    wire = encoded(command)
    selected = credentials["OPERATOR_KEY" if credential == "operator" else "AUTHORITY_KEY"]
    with httpx.Client(trust_env=False) as client:
        response = client.post(
            endpoint,
            content=wire,
            headers={
                "content-type": "application/json",
                "x-livia-role": credential,
                "x-livia-signature": hmac.new(selected.encode(), wire, hashlib.sha256).hexdigest(),
            },
            timeout=15,
            follow_redirects=False,
        )
    raw = response.json()
    payload = raw["payload"]
    VerifyKey(bytes.fromhex(identity["public_key"])).verify(
        encoded(payload), bytes.fromhex(raw["signature"])
    )
    if (
        payload["nonce"] != command["nonce"]
        or payload["scope"] != identity["scope"]
        or payload["account"] != identity["account"]
        or abs(payload["served_at"] - time() * 1000) > 15000
    ):
        raise ValueError("cloudflare_receipt_unverified")
    return payload


def canary():
    primary = raw_command("authority", "inspect", {})
    enrolled = raw_command(
        "canary",
        "enroll",
        {
            "authority_account": primary["account"],
            "digest": primary["digest"],
            "snapshot": primary["state"],
        },
        expected=0,
    )
    if not enrolled["ok"]:
        raise ValueError("canary_already_enrolled_or_unavailable")
    snapshot = {**primary["state"], "revision": 1}
    first = raw_command(
        "canary",
        "advance",
        {
            "authority_account": primary["account"],
            "prior_digest": primary["digest"],
            "digest": hashlib.sha256(encoded(snapshot)).hexdigest(),
            "snapshot": snapshot,
        },
        credential="authority",
        expected=0,
    )
    replay = raw_command(
        "canary",
        "advance",
        {
            "authority_account": primary["account"],
            "prior_digest": primary["digest"],
            "digest": primary["digest"],
        },
        credential="authority",
        expected=0,
    )
    denied = raw_command("authority", "read", {})
    after = raw_command("authority", "inspect", {})
    if (
        not first["ok"]
        or replay["ok"]
        or denied["ok"]
        or denied.get("error") != "administration_not_independent"
        or after["digest"] != primary["digest"]
    ):
        raise ValueError("canary_safety_assertion_failed")
    result = {
        "live_cloudflare_witness_transaction": first["ok"],
        "same_account_authority_denied": not denied["ok"],
        "authority_root_unchanged": after["digest"] == primary["digest"],
        "stale_cas_denied": not replay["ok"],
        "independent_administration": False,
        "operational_egress": False,
        "contains_customer_content": False,
    }
    private_write(PRIVATE / "canary-evidence.json", result)
    print(json.dumps(result))


def operator(action, proof_file=None):
    configured = read_private(Path(".local/b3/operator.json"))
    authority = CloudflareAuthority(AuthorityConfig(**configured["runtime"]))
    if action == "repair-roots":
        values = config()
        pending = []
        fault_path = Path(".local/b1/control/authority-faults.jsonl")
        if fault_path.exists():
            for line in fault_path.read_bytes().splitlines():
                record = json.loads(line)
                mac = record.pop("mac")
                if not hmac.compare_digest(
                    mac,
                    hmac.new(
                        values["WAHA_JOURNAL_KEY"].encode(), encoded(record), hashlib.sha256
                    ).hexdigest(),
                ):
                    raise ValueError("local_fault_record_unverified")
                if record.get("participant"):
                    pending.append(record["participant"])
        authority.repair(configured["operator_key"], revocations=pending)
        print('{"repaired":true,"paused":true,"new_submission":false}')
        return
    state = authority.read()
    if action == "status":
        print(
            json.dumps(
                {
                    "epoch": state["epoch"],
                    "paused": state["paused"],
                    "killed": state["killed"],
                    "intents": len(state["intents"]),
                }
            )
        )
        return
    if action == "kill":
        authority.command("kill", {}, operator_key=configured["operator_key"])
        operator_request(config(), "pause")
        print('{"killed":true}')
        return
    values = config()
    ready = operator_request(values, "ready")
    if (
        (action == "release-first" and ready.get("paused") is not False)
        or not ready.get("connected_secondary")
        or ready.get("authority_epoch") != state["epoch"]
    ):
        raise ValueError("backend_epoch_identity_or_pause_unverified")
    channel = api(values)
    initial = channel.session_info()
    verified = {}
    for phone in (values["WAHA_SECONDARY_PHONE"], *json.loads(values["WAHA_AUTHORIZED_PHONES"])):
        for alias in channel.identities_for(phone):
            if alias in verified and verified[alias] != phone_chat(phone):
                raise ValueError("identity_collision")
            verified[alias] = phone_chat(phone)
    current = channel.session_info()
    if (
        current.get("status") != "WORKING"
        or current.get("me") != initial.get("me")
        or verified.get((current.get("me") or {}).get("id"))
        != phone_chat(values["WAHA_SECONDARY_PHONE"])
    ):
        raise ValueError("secondary_identity_unverified")
    _, head, _ = current_scope(values)
    if action == "reconcile-accepted":
        proof = read_private(Path(proof_file))
        identity, provider_id = proof["intent"], proof["provider_message_id"]
        entry = state["intents"].get(identity)
        if not entry or entry["outcome"] != "accepted":
            raise ValueError("external_causal_acceptance_receipt_required")
        with sqlite3.connect(
            Path(".local/b1/backend/conversations.db").resolve().as_uri() + "?mode=ro", uri=True
        ) as connection:
            rows = connection.execute(
                "SELECT i.provider_message_id,d.provider_channel_id,d.recipient_address,o.body "
                "FROM outbound_deliveries d JOIN messages o ON o.id=d.outbound_message_id "
                "JOIN messages i ON i.id=o.in_reply_to_message_id "
                "WHERE d.provider='waha' AND d.state IN ('unknown','sending') "
                "AND d.first_submission_at IS NOT NULL"
            ).fetchall()
        row = next(
            (
                r
                for r in rows
                if hmac.new(
                    values["WAHA_JOURNAL_KEY"].encode(),
                    encoded(["waha", r[1], r[0], "service_response"]),
                    hashlib.sha256,
                ).hexdigest()
                == identity
            ),
            None,
        )
        if row is None:
            raise ValueError("local_unknown_intent_required")
        message = OutboundMessage(row[1], row[2], row[3], submission_key=entry["key"])
        if hashlib.sha256(prepare_waha(message)).hexdigest() != entry["digest"]:
            raise ValueError("local_request_digest_mismatch")
        evidence = observe_waha_acceptance(
            channel, verified, message, provider_id, submission=entry
        )
        authority.read()
        authority.command(
            "reconcile",
            {
                "intent": identity,
                "digest": entry["digest"],
                "token": entry["token"],
                "evidence": evidence,
                "acceptance": hashlib.sha256(provider_id.encode()).hexdigest(),
                "outcome": "accepted",
            },
            operator_key=configured["operator_key"],
        )
        with httpx.Client(trust_env=False) as client:
            result = client.post(
                "http://127.0.0.1:8001/ops/waha/reconcile",
                headers={"Authorization": "Bearer " + values["WAHA_OPERATOR_TOKEN"]},
                json={"intent": identity, "provider_message_id": provider_id},
                timeout=45,
            )
        if result.status_code != 200 or result.json().get("reconciled") is not True:
            raise ValueError("external_fact_saved_local_reconciliation_pending")
        print('{"reconciled":true,"new_submission":false}')
        return
    with sqlite3.connect(
        Path(".local/b1/backend/conversations.db").resolve().as_uri() + "?mode=ro", uri=True
    ) as connection:
        rows = connection.execute(
            "SELECT i.provider_message_id,d.provider_channel_id,d.recipient_address "
            "FROM outbound_deliveries d JOIN messages o ON o.id=d.outbound_message_id "
            "JOIN messages i ON i.id=o.in_reply_to_message_id "
            "WHERE d.provider='waha' AND d.state='pending' "
            "AND d.first_submission_at IS NULL ORDER BY d.id"
        ).fetchall()
    if len(rows) != 1 or rows[0][2] not in {
        phone_chat(p) for p in json.loads(values["WAHA_AUTHORIZED_PHONES"])
    }:
        raise ValueError("exactly_one_authorized_unsubmitted_reply_required")
    inbound, secondary, recipient = rows[0]
    identity = hmac.new(
        values["WAHA_JOURNAL_KEY"].encode(),
        encoded(["waha", secondary, inbound, "service_response"]),
        hashlib.sha256,
    ).hexdigest()
    state = authority.read()
    authority.command(
        "release",
        {
            "boot": state["boot"],
            "epoch": state["epoch"],
            "head": head,
            "intent": identity,
            "participant": hashlib.sha256(recipient.encode()).hexdigest(),
            "expires_at": int(time() * 1000) + 600000,
        },
        operator_key=configured["operator_key"],
    )
    # Refresh the backend's optimistic CAS revision after this operator mutation.
    result = operator_request(values, "ready")
    print(
        json.dumps(
            {
                "released_first_reply": result.get("egress") is True,
                "remaining_scope": "one_current_intent_only",
            }
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=(
            "prepare",
            "deploy-authority",
            "deploy-canary",
            "canary-check",
            "status",
            "release-first",
            "kill",
            "repair-roots",
            "reconcile-accepted",
        ),
    )
    parser.add_argument("--proof-file")
    parsed = parser.parse_args()
    action = parsed.action
    try:
        if action == "prepare":
            prepare()
        elif action.startswith("deploy-"):
            deploy(action.removeprefix("deploy-"))
        elif action == "canary-check":
            canary()
        else:
            operator(action, parsed.proof_file)
    except Exception as error:
        safe = (
            str(error)
            if isinstance(error, ValueError) and re.fullmatch(r"[a-z_]{3,100}", str(error))
            else type(error).__name__
        )
        print(json.dumps({"error": safe, "whatsapp_egress": False}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
