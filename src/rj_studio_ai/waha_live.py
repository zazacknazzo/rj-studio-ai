"""Explicit private WAHA entry point; existing providers/main remain unchanged."""

import hashlib
import hmac
import json
import re
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import anyio
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import Field

from rj_studio_ai.application import MessageResponder
from rj_studio_ai.config import Settings
from rj_studio_ai.conversation_context import ConversationContextBuilder, ConversationContextLimits
from rj_studio_ai.generation import GenerationFailure
from rj_studio_ai.persistence import DeliveryState, PersistenceUnavailable
from rj_studio_ai.processing import ProcessingExecutor, ProcessingRunner
from rj_studio_ai.providers.base import (
    InvalidWebhookPayload,
    InvalidWebhookSignature,
    ProviderWebhookRequest,
)
from rj_studio_ai.providers.openai_contract import response_request
from rj_studio_ai.providers.waha import WahaAdapter, WahaAPI, WahaIdentityError, phone_chat
from rj_studio_ai.runtime import generator_from_settings
from rj_studio_ai.salon_knowledge import SalonKnowledgeRepository
from rj_studio_ai.waha_safety import WahaConversationStore, WahaSafetyError, WahaSafetyJournal


class WahaSettings(Settings):
    llm_provider: str = "openai"
    waha_secondary_phone: str = Field(default="", repr=False, exclude=True)
    waha_authorized_phones: tuple[str, ...] = Field(default=(), repr=False, exclude=True)
    waha_api_url: str = "http://127.0.0.1:3000"
    waha_api_key: str = Field(default="", repr=False, exclude=True)
    waha_webhook_secret: str = Field(default="", repr=False, exclude=True)
    waha_operator_token: str = Field(default="", repr=False, exclude=True)
    waha_journal_key: str = Field(default="", repr=False, exclude=True)
    waha_state_path: Path = Path(".local/b1/backend/conversations.db")
    waha_control_path: Path = Path(".local/b1/control")
    waha_witness_path: Path = Path(".local/b1/witness/head.json")


def require_test_secondary(secondary, knowledge_path):
    knowledge = SalonKnowledgeRepository(knowledge_path)
    for fact in knowledge.load():
        if fact.category.value != "channel":
            continue
        for candidate in re.findall(r"\(?\d{2}\)?\s*\d{4,5}[-\s]?\d{4}", fact.statement):
            digits = re.sub(r"\D", "", candidate)
            if secondary == "+55" + digits:
                raise ValueError("salon_public_number_is_forbidden_for_private_test")


class BudgetedOpenAI:
    """Decorates the existing real factory generator; never substitutes a decision."""

    def __init__(self, settings, journal):
        if settings.llm_provider != "openai":
            raise ValueError("waha_requires_openai")
        self.generator = generator_from_settings(settings)
        self.settings, self.journal = settings, journal

    def is_configured(self):
        return self.generator.is_configured()

    def generate(self, message, *, context, remaining_budget):
        if not self.journal.permits_generation(message.customer_address):
            raise GenerationFailure("waha_paused_or_revoked")
        wire = response_request(
            message,
            context,
            model=self.settings.openai_model,
            reasoning_effort=self.settings.openai_reasoning_effort,
            max_output_tokens=self.settings.openai_max_output_tokens,
        )
        # UTF-8 request bytes + protocol margin conservatively bound model tokens.
        input_bound = len(json.dumps(wire, ensure_ascii=False).encode()) + 1024
        self.journal.reserve(
            input_tokens=input_bound, output_tokens=self.settings.openai_max_output_tokens
        )
        try:
            generated = self.generator.generate(
                message, context=context, remaining_budget=remaining_budget
            )
        except GenerationFailure as error:
            metric = error.metric
            known = metric is not None and metric.input_tokens is not None
            self.journal.settle(known=known)
            raise
        except BaseException:
            self.journal.settle(known=False)
            raise
        metric = generated.metric
        known = (
            metric is not None
            and metric.input_tokens is not None
            and metric.output_tokens is not None
            and metric.input_tokens <= input_bound
            and metric.output_tokens <= self.settings.openai_max_output_tokens
        )
        self.journal.settle(known=known)
        if not known:
            raise GenerationFailure("waha_usage_unverified", metric)
        # Retain the canonical runtime metric. Estimated cost stays null without a
        # current approved runtime table; the journal records a versioned ceiling.
        return replace(generated, metric=metric)


def _change_core_pause(store, action, participant=None):
    with store._connect() as connection:
        rows = connection.execute(
            "SELECT ids.opaque_id,conversations.customer_address FROM conversation_operation_ids "
            "AS ids JOIN conversations ON conversations.id=ids.conversation_id "
            "WHERE conversations.provider='waha'"
        ).fetchall()
    for opaque_id, customer in rows:
        if participant is not None and customer != participant:
            continue
        if action == "resume" and not store.journal.permits_generation(customer):
            continue
        state = store.get_automation_state(opaque_id)
        if state["paused"] == (action == "pause"):
            continue
        store.change_automation(opaque_id, action, uuid4().hex, state["revision"], "b1-local")


def build_waha_pipeline(
    settings, *, journal_factory=WahaSafetyJournal, store_factory=WahaConversationStore
):
    if len(settings.waha_operator_token) < 32:
        raise ValueError("waha_operator_token_required")
    require_test_secondary(settings.waha_secondary_phone, settings.salon_knowledge_path)
    adapter = WahaAdapter(
        secret=settings.waha_webhook_secret,
        secondary=settings.waha_secondary_phone,
        participants=settings.waha_authorized_phones,
    )
    journal = journal_factory(
        settings.waha_control_path,
        settings.waha_witness_path,
        key=settings.waha_journal_key,
        scope={
            "secondary": adapter.secondary,
            "participants": sorted(adapter.participants),
            "model": settings.openai_model,
            "reasoning": settings.openai_reasoning_effort,
            "max_output": settings.openai_max_output_tokens,
            "knowledge": hashlib.sha256(settings.salon_knowledge_path.read_bytes()).hexdigest(),
            "call_cap": 20,
            "token_cap": 500_000,
            "cost_estimate_cap_microusd": 1_000_000,
        },
    )
    try:
        settings.waha_state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        store = store_factory(settings.waha_state_path, journal=journal)
        store.initialize()
        knowledge = SalonKnowledgeRepository(settings.salon_knowledge_path)
        knowledge.load()
        generator = BudgetedOpenAI(settings, journal)
        context = ConversationContextBuilder(
            store=store,
            salon_knowledge=knowledge,
            limits=ConversationContextLimits(
                maximum_prior_messages=settings.conversation_context_maximum_messages,
                history_token_budget=settings.conversation_context_history_token_budget,
                total_input_token_budget=settings.llm_input_token_budget,
                use_history_for_knowledge=True,
            ),
        )
        responder = MessageResponder(
            store=store,
            generator=generator,
            safe_failure_reply="Vou chamar a equipe para te ajudar.",
            context_builder=context,
            completion_delivery_state=DeliveryState.PENDING,
        )
        runner = ProcessingRunner(store=store, responder=responder)
        return adapter, journal, store, knowledge, generator, context, runner
    except BaseException:
        journal.close()
        raise


def create_waha_app(settings=None, *, pipeline_builder=build_waha_pipeline, outbound_factory=None):
    settings = settings or WahaSettings(_env_file=".env.b1")
    adapter, journal, store, knowledge, generator, context, runner = pipeline_builder(settings)
    api = WahaAPI(base_url=settings.waha_api_url, api_key=settings.waha_api_key)
    processing = ProcessingExecutor(runner=runner, poll_interval_seconds=0.25, concurrency=1)
    outbound = outbound_factory(adapter, journal, store, api) if outbound_factory else None

    @asynccontextmanager
    async def lifespan(app):
        if generator.is_configured():
            processing.start()
        if outbound is not None:
            outbound.start()
        try:
            yield
        finally:
            await anyio.to_thread.run_sync(processing.stop)
            try:
                if outbound is not None:
                    await anyio.to_thread.run_sync(outbound.stop)
                journal.change("pause")
            finally:
                journal.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store, app.state.journal = store, journal
    app.state.processing_executor = processing
    app.state.context_builder = context
    # Structural: no Outbound Executor or permissive store is composed.
    app.state.outbound_executor = outbound

    def require_operator(request):
        if not hmac.compare_digest(
            request.headers.get("authorization", ""), "Bearer " + settings.waha_operator_token
        ):
            raise HTTPException(403, "operator_authentication")

    @app.get("/health")
    def health():
        return {"process": "ok", "channel": "waha-private"}

    @app.get("/ready")
    def ready(request: Request):
        require_operator(request)
        try:
            journal.refresh()
            connected = False
            try:
                info = api.session_info()
                connected = (
                    info.get("status") == "WORKING"
                    and adapter.identity_aliases.get(info.get("me", {}).get("id"))
                    == adapter.secondary
                )
            except Exception:
                pass
            payload = {
                "ingress": True,
                "knowledge_facts": len(knowledge.load()),
                "openai_configured": generator.is_configured(),
                "processing": processing.is_alive(),
                "connected_secondary": connected,
                "paused": journal.paused,
                "calls_reserved": journal.calls,
                "token_reservation": journal.reserved_tokens,
                "cost_reservation_microusd": journal.reserved_microusd,
                "unresolved_model_call": journal.unresolved,
                "egress": False,
                "egress_blockers": ["AUD-01", "AR-02"],
                "whatsapp_conversation_proven": False,
            }
            if outbound is not None:
                payload.update(store.egress_status())
                payload["outbound"] = outbound.is_alive()
            return JSONResponse(payload, status_code=503)
        except WahaSafetyError:
            return JSONResponse(
                {"egress": False, "error": "safety_integrity_failed"}, status_code=503
            )

    @app.post("/ops/{action}")
    def operation(action: str, request: Request):
        require_operator(request)
        if action not in {"pause", "resume"}:
            raise HTTPException(404, "operation_not_found")
        if action == "resume":
            # Revalidation is fail-closed, including when already resumed.
            with journal.lock:
                journal.change("pause")
                _change_core_pause(store, "pause")
                adapter.bind_verified_identities({})
                control_revision = journal.control_revision
            if not generator.is_configured():
                raise HTTPException(409, "configure_OPENAI_API_KEY_in_private_env")
            try:
                info = api.session_info()
                if info.get("status") != "WORKING":
                    raise WahaIdentityError("waha_session_not_working")
                verified = {}
                for number in (settings.waha_secondary_phone, *settings.waha_authorized_phones):
                    for alias in api.identities_for(number):
                        canonical = phone_chat(number)
                        if alias in verified and verified[alias] != canonical:
                            raise WahaIdentityError("waha_identity_collision")
                        verified[alias] = canonical
                # Contact checks may take seconds; a disconnect/rebind meanwhile
                # must not authorize the account seen only before those reads.
                current = api.session_info()
                if (
                    current.get("status") != "WORKING"
                    or (current.get("me") or {}).get("id") != (info.get("me") or {}).get("id")
                    or verified.get((current.get("me") or {}).get("id")) != adapter.secondary
                ):
                    raise WahaIdentityError("waha_session_identity_unverified")
                with journal.lock:
                    journal.refresh()
                    if journal.control_revision != control_revision:
                        raise WahaIdentityError("waha_controls_changed_during_verification")
                    journal.append(
                        {
                            "kind": "identities",
                            "digest": hashlib.sha256(
                                json.dumps(verified, sort_keys=True).encode()
                            ).hexdigest(),
                        }
                    )
                    adapter.bind_verified_identities(verified)
                    journal.change(action)
                    _change_core_pause(store, action)
            except WahaIdentityError as error:
                raise HTTPException(409, str(error)) from None
            except Exception:
                journal.change("pause")
                raise HTTPException(409, "secondary_session_not_connected") from None
        else:
            journal.change(action)
            _change_core_pause(store, action)
        processing.wake()
        return {"paused": journal.paused, "egress": False, "scope": "inference_only"}

    @app.post("/webhooks/waha")
    async def webhook(request: Request):
        selected = {}
        headers = request.scope["headers"]
        if len(headers) > 100 or sum(len(k) + len(v) for k, v in headers) > 16_384:
            raise HTTPException(431, "webhook_headers_too_large")
        sensitive = {"x-webhook-hmac", "x-webhook-hmac-algorithm", "content-type", "content-length"}
        for key, value in request.scope["headers"]:
            name = key.decode("latin1").lower()
            if name in sensitive:
                if name in selected:
                    raise HTTPException(400, "duplicate_header")
                selected[name] = value.decode("latin1")
        if selected.get("content-type", "").split(";", 1)[0] != "application/json":
            raise HTTPException(415, "json_required")
        body = bytearray()
        try:
            with anyio.fail_after(1):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > 65_536:
                        raise HTTPException(413, "webhook_too_large")
                    body.extend(chunk)
        except TimeoutError:
            raise HTTPException(408, "webhook_timeout") from None
        try:
            observation = adapter.observe(
                ProviderWebhookRequest(
                    method="POST",
                    url="http://backend/webhooks/waha",
                    headers=selected,
                    query_string=b"",
                    content_type="application/json",
                    body=bytes(body),
                )
            )
        except InvalidWebhookSignature:
            raise HTTPException(403, "webhook_authentication") from None
        except InvalidWebhookPayload:
            raise HTTPException(422, "webhook_invalid") from None

        def persist():
            with journal.lock:
                if observation.disconnected:
                    journal.change("pause")
                    _change_core_pause(store, "pause")
                if observation.opt_out:
                    journal.change("revoke", observation.participant)
                if observation.batch.events:
                    store.record_webhook_events(
                        observation.batch.events, require_message_provenance=True
                    )
                    for event in observation.batch.events:
                        if observation.opt_out:
                            _change_core_pause(store, "pause", event.customer_address)
                        if not journal.permits_generation(event.customer_address):
                            lifecycle = store.get_generation(
                                provider="waha", provider_message_id=event.provider_message_id
                            )
                            if lifecycle and lifecycle.state.value in {"pending", "retryable"}:
                                store.suppress_generation(event)

        try:
            await anyio.to_thread.run_sync(persist)
        except (PersistenceUnavailable, ValueError):
            raise HTTPException(503, "webhook_persistence_unavailable") from None
        processing.wake()
        return Response(status_code=204)

    return app
