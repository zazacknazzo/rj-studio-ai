"""Closed G0 test harness. Application components are real; LLM/provider are fixtures.

No entry point, credentials, existing database, transport or model can be supplied.
The offline ASGI store stays quarantined. A second legacy store handle, restricted
to this private synthetic database and fixed fake exchange, exercises T10/T11.
That historical test seam is NOT an operational antirollback/release mechanism.
"""

import base64
import json
import os
import secrets
import socket
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from starlette.testclient import TestClient
from telnyx_channel_fixture import verified_channel, verified_consent
from test_telnyx_authentication import ORG, PHONE, PROFILE, WABA, signed
from test_telnyx_delivery_status import status_wire
from test_telnyx_lifecycle import account
from test_telnyx_messages import CUSTOMER, wire
from test_telnyx_sender import acceptance, response

from rj_studio_ai.application import MessageResponder
from rj_studio_ai.config import Settings
from rj_studio_ai.conversation_context import ConversationContextBuilder, ConversationContextLimits
from rj_studio_ai.delivery import OutboundDeliveryRunner
from rj_studio_ai.generation import GeneratedReply
from rj_studio_ai.llm_decision import LLMDecision
from rj_studio_ai.persistence import DeliveryState, SqliteConversationStore
from rj_studio_ai.processing import ProcessingRunner
from rj_studio_ai.providers.telnyx_sender import TelnyxWhatsAppSender
from rj_studio_ai.salon_knowledge import SalonKnowledgeRepository
from rj_studio_ai.telnyx_asgi import create_telnyx_offline_app
from rj_studio_ai.telnyx_request import TelnyxRequestSigner

FACTS = {
    "g0-hours": ("hours", "salão", "[DADO SINTÉTICO] O salão atende de terça a sábado."),
    "g0-progressiva": ("service", "progressiva", "[DADO SINTÉTICO] Oferecemos progressiva."),
    "g0-price": (
        "price",
        "progressiva",
        "[DADO SINTÉTICO] O preço depende de avaliação da equipe.",
    ),
}
UNTRUSTED_PROSE = "FIXTURE_FREE_PROSE_NAO_PUBLICAR: agendei por R$ 999."


def decision(intent="greeting", *, fact=None, **overrides):
    """An untrusted LLMDecision fixture; never a GeneratedReply.trusted_reply."""
    return LLMDecision.model_validate(
        {
            "intents": [intent],
            "reply_text": UNTRUSTED_PROSE,
            "reply_parts": [
                {"kind": "phrase", "phrase": "greeting" if intent == "greeting" else "help"},
                *([{"kind": "fact", "knowledge_ref": fact}] if fact else []),
            ],
            "uncertainty": "low",
            "knowledge_refs": [fact] if fact else [],
            "critical_claims": [],
            "handoff": False,
            "handoff_reason": None,
            **overrides,
        }
    )


class ScriptedDecisionFixture:
    """No inference: explicit proposal, context capture and optional test rendezvous."""

    def __init__(self):
        self.proposal = decision()
        self.contexts = []
        self.before_return = None
        self.failure = None

    def is_configured(self):
        return True

    def generate(self, message, *, context, remaining_budget):
        self.contexts.append(context)
        if self.before_return is not None:
            self.before_return()
        if self.failure is not None:
            raise self.failure
        return GeneratedReply(decision=self.proposal)


def require_network_guard():
    if os.environ.get("TICKET13_NETWORK_GUARD") != "active":
        raise RuntimeError("G0 requires scripts/check_telnyx_offline.py")
    # Check effective interception instead of trusting an environment flag alone.
    for family, address in ((socket.AF_INET, ("127.0.0.1", 9)), (socket.AF_INET6, ("::1", 9))):
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            try:
                probe.connect(address)
            except RuntimeError as error:
                if str(error) == "TICKET13_IP_NETWORK_BLOCKED":
                    continue
                raise
            raise RuntimeError("G0 network guard is ineffective")
    try:
        socket.getaddrinfo("g0.invalid", 443)
    except RuntimeError as error:
        if str(error) == "TICKET13_IP_NETWORK_BLOCKED":
            return
        raise
    raise RuntimeError("G0 DNS guard is ineffective")


class G0Staging:
    def __init__(self, private_directory: Path):
        require_network_guard()
        self.root = private_directory / "g0"
        self.root.mkdir(mode=0o700)  # refuse reuse of any previous database
        self.path = self.root / "synthetic.db"
        self.now = datetime.now(UTC).replace(microsecond=0)
        self.key = Ed25519PrivateKey.generate()  # ephemeral; never written to evidence
        self.settings = Settings(
            _env_file=None,
            delivery_mode="proactive",
            telnyx_public_key=base64.b64encode(self.key.public_key().public_bytes_raw()).decode(),
            telnyx_phone_number=PHONE,
            telnyx_messaging_profile_id=PROFILE,
            telnyx_waba_id=WABA,
            telnyx_organization_id=ORG,
        )
        self.app = create_telnyx_offline_app(
            self.settings, self.path, wall_clock=lambda: self.now.timestamp()
        )
        verified_channel(self.path)
        verified_consent(self.path, customer=CUSTOMER, now=self.now)
        self.signer = TelnyxRequestSigner(ORG, PROFILE, "g0-ephemeral", secrets.token_bytes(32))
        self.store = SqliteConversationStore(self.path, telnyx_request_signer=self.signer)
        self.model = ScriptedDecisionFixture()
        source = self.root / "synthetic-knowledge.yaml"
        source.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "facts": [
                        {
                            "id": identifier,
                            "category": category,
                            "topic": topic,
                            "status": "approved",
                            "fact_type": "operational_commercial",
                            "statement": statement,
                            "source": "G0 synthetic fixture only",
                            "reviewed_at": "2026-11-22",
                            "approved_by": "synthetic operator; no real salon approval",
                        }
                        for identifier, (category, topic, statement) in FACTS.items()
                    ],
                },
                allow_unicode=True,
            )
        )
        knowledge = SalonKnowledgeRepository(source)
        knowledge.load()
        self.context_builder = ConversationContextBuilder(
            store=self.store, salon_knowledge=knowledge, limits=ConversationContextLimits()
        )
        self.processor = ProcessingRunner(
            self.store,
            MessageResponder(
                store=self.store,
                generator=self.model,
                safe_failure_reply="[FALLBACK DETERMINÍSTICO] A equipe vai ajudar você.",
                context_builder=self.context_builder,
                completion_delivery_state=DeliveryState.PENDING,
            ),
        )
        self.requests = []
        self.transport_outcome = "accept"
        self.sender = TelnyxWhatsAppSender(self.signer, self._fake_exchange)
        self.outbound = OutboundDeliveryRunner(self.store, self.sender, 9, provider="telnyx")
        self.turns = []

    def _fake_exchange(self, request, **policy):
        assert self.signer.verify(request)
        assert policy == {
            "connect_timeout_seconds": 3,
            "read_timeout_seconds": 6,
            "retries": 0,
            "follow_redirects": False,
        }
        # A new SQLite writer succeeds: no application transaction spans transport.
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            marker = db.execute(
                "SELECT submission_started_at FROM outbound_deliveries WHERE submission_key=?",
                (request.message.submission_key,),
            ).fetchone()
            assert marker is not None and marker[0] is not None
            assert db.execute(
                "SELECT COUNT(*) FROM telnyx_http_requests WHERE submission_key=?",
                (request.message.submission_key,),
            ).fetchone() == (1,)
        self.requests.append(request)
        if self.transport_outcome == "timeout":
            raise TimeoutError("synthetic transport timeout")
        if self.transport_outcome == "ambiguous":
            return response({"data": {}}, 200)
        result = acceptance(request)
        result["data"]["id"] = f"g0-fake-acceptance-{len(self.requests)}"
        return response(result)

    def post(self, payload, *, corrupt=False):
        request = signed(self.key, payload, timestamp=str(int(self.now.timestamp())))
        with TestClient(self.app) as client:
            return client.post(
                "/webhooks/telnyx",
                content=request.body + (b" " if corrupt else b""),
                headers={"content-type": request.content_type, **request.headers},
            )

    def inbound(self, text, *, identifier=None, kind="text"):
        number = identifier or str(len(self.turns) + 1)
        envelope = wire(
            kind,
            event_id=f"g0-event-{number}",
            message_id=f"g0-inbound-{number}",
            occurred=int(self.now.timestamp()),
            source=int(self.now.timestamp()) - 1,
        )
        body = envelope["data"]["payload"]["body"]
        body["foreign_id"] = f"wamid.g0-{number}"
        body["text"] = {"body": text}
        assert self.post(envelope).status_code == 204
        if kind == "text":
            self.turns.append({"customer_synthetic": text, "message_id": f"g0-inbound-{number}"})
        return envelope

    def process(self, proposal=None):
        if proposal is not None:
            self.model.proposal = proposal
        result = self.processor.run_once()
        self.now = max(self.now, datetime.now(UTC))
        return result

    def deliver(self):
        self.now = max(self.now, datetime.now(UTC)) + timedelta(seconds=1)
        return self.outbound.run_once(now=self.now)

    def status(self, delivery, status="delivered"):
        envelope = status_wire(
            status,
            message_id=delivery.provider_message_id,
            event_id=f"g0-status-{delivery.delivery_id}-{status}",
        )
        envelope["data"]["occurred_at"] = self.now.isoformat()
        assert self.post(envelope).status_code == 204
        return self.store.get_delivery(delivery.delivery_id)

    def lifecycle(self, transition):
        return self.post(account(transition, event_id=f"g0-{transition}", occurred=self.now))

    def revoke(self):
        # Synthetic authoritative consent update, not text understanding or a live API.
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE telnyx_consent SET revoked_at=?", (self.now.isoformat(),))

    def rows(self, table):
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(f"SELECT * FROM {table}")]

    def report(self, scenario, **observations):
        history = self.store.get_history(provider="telnyx", customer_address=CUSTOMER)
        data = {
            "scenario": scenario,
            "application": "real ASGI/auth/normalization/SQLite/processing/grounding/authorization",
            "llm": "scripted LLMDecision fixture; no model call",
            "knowledge": "synthetic fixtures; not real salon facts",
            "provider": "fixed intercepted exchange; fake acceptance and signed fake statuses",
            "operational_egress": False,
            "aud_01": "OPEN",
            "turns": self.turns,
            "history": [{"direction": row.direction, "body": row.body} for row in history],
            "transport_calls": len(self.requests),
            "processing_states": [row["state"] for row in self.rows("message_processing")],
            "delivery_states": [row["state"] for row in self.rows("outbound_deliveries")],
            "observations": observations,
        }
        (self.root.parent / "g0-report.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        )
        return data
