"""Only trusted policy can turn a model proposal into operational handoff."""

import pytest

from rj_studio_ai.application import ExecutionDeadline
from rj_studio_ai.conversation_context import ConversationContext
from rj_studio_ai.grounding import finalize_reply
from rj_studio_ai.llm_decision import LLMDecision


def proposal(**overrides):
    return LLMDecision.model_validate(
        {
            "intents": ["greeting"],
            "reply_text": "Untrusted model text",
            "reply_parts": [{"kind": "phrase", "phrase": "help"}],
            "knowledge_refs": [],
            "critical_claims": [],
            "uncertainty": "low",
            "handoff": True,
            "handoff_reason": "model_requested_handoff",
            **overrides,
        }
    )


def test_benign_greeting_renders_normally_despite_model_handoff_proposal():
    result = finalize_reply(proposal(), customer_message="Oi", context=ConversationContext((), ()))
    assert not result.handoff and result.handoff_reason is None
    assert result.reply_text == "Como posso te ajudar?"
    assert result.intents == proposal().intents


class AdvisoryModel:
    def __init__(self, decision=None):
        self.decision = decision or proposal()
        self.contexts = []

    def generate(self, message, *, context, remaining_budget):
        from rj_studio_ai.generation import GeneratedReply

        self.contexts.append(context)
        return GeneratedReply(decision=self.decision)


def test_other_benign_intent_preserves_safe_plan_not_a_terminal_model_proposal():
    decision = proposal(intents=["other"], handoff_reason="arbitrary private model reason")
    result = finalize_reply(
        decision, customer_message="Queria saber uma coisa", context=ConversationContext((), ())
    )
    assert not result.handoff and result.handoff_reason is None
    assert result.reply_text == "Como posso te ajudar?"
    assert decision.handoff  # The original proposal remains available to the observer.


def test_authorization_changes_only_the_advisory_handoff_fields():
    from rj_studio_ai.handoff import apply_handoff_policy

    decision = proposal()
    result = apply_handoff_policy(decision)
    assert result.model_dump(exclude={"handoff", "handoff_reason"}) == decision.model_dump(
        exclude={"handoff", "handoff_reason"}
    )
    assert result.handoff is False and result.handoff_reason is None


def test_unknown_reason_is_normalized_for_privacy_but_not_authorized():
    from rj_studio_ai.handoff import HandoffReason, apply_handoff_policy, safe_handoff_reason

    normalized = safe_handoff_reason("private unverified model explanation")
    assert normalized is HandoffReason.MODEL_REQUEST
    assert not apply_handoff_policy(proposal(), required_reason=normalized).handoff


def message(identifier, body):
    from rj_studio_ai.domain import InboundMessage

    return InboundMessage("test-provider", identifier, "synthetic-customer", "studio", body)


def responder(store, model, context_builder=None):
    from rj_studio_ai.application import MessageResponder
    from rj_studio_ai.persistence import DeliveryState

    return MessageResponder(
        store=store,
        generator=model,
        context_builder=context_builder,
        safe_failure_reply="Fallback",
        completion_delivery_state=DeliveryState.ACCEPTED_LEGACY,
    )


def empty_knowledge_builder(store, tmp_path):
    from rj_studio_ai.conversation_context import (
        ConversationContextBuilder,
        ConversationContextLimits,
    )
    from rj_studio_ai.salon_knowledge import SalonKnowledgeRepository

    path = tmp_path / "synthetic.yaml"
    path.write_text("version: 1\nfacts: []\n")
    repository = SalonKnowledgeRepository(path)
    repository.load()
    return ConversationContextBuilder(
        store=store, salon_knowledge=repository, limits=ConversationContextLimits()
    )


@pytest.mark.parametrize(
    "body", ["Oi", "Bom dia", "Obrigada", "Tudo bem?", "Queria saber uma coisa"]
)
def test_benign_messages_do_not_persist_a_model_only_handoff(tmp_path, body):
    from rj_studio_ai.persistence import SqliteConversationStore

    store = SqliteConversationStore(tmp_path / "benign.db")
    store.initialize()
    reply = responder(store, AdvisoryModel()).handle(
        message("benign-1", body), deadline=ExecutionDeadline.start()
    )
    assert reply.body == "Como posso te ajudar?"
    assert store.list_active_handoffs() == []


@pytest.mark.parametrize("restart", [False, True])
def test_release_preserves_history_and_cannot_reopen_on_benign_model_proposal(tmp_path, restart):
    from rj_studio_ai.persistence import GenerationState, SqliteConversationStore

    path = tmp_path / "release.db"
    store = SqliteConversationStore(path)
    store.initialize()
    model = AdvisoryModel(proposal(handoff=False, handoff_reason=None))
    first = responder(store, model, empty_knowledge_builder(store, tmp_path)).handle(
        message("human-1", "Quero falar com uma pessoa."), deadline=ExecutionDeadline.start()
    )
    handoff = store.list_active_handoffs()[0]
    assert handoff.reason_code == "explicit_human_request"
    assert (
        responder(store, model).handle(
            message("suppressed-2", "Ainda aguardando"), deadline=ExecutionDeadline.start()
        )
        is None
    )
    assert len(model.contexts) == 1
    assert store.release_handoff(
        conversation_id=handoff.conversation_id, owner_token=handoff.owner_token
    )
    if restart:
        store = SqliteConversationStore(path)
    model.decision = proposal()
    service = responder(store, model, empty_knowledge_builder(store, tmp_path))
    inbound = message("greeting-3", "Oi")
    reply = service.handle(inbound, deadline=ExecutionDeadline.start())
    assert reply.body == "Como posso te ajudar?"
    assert store.list_active_handoffs() == []
    history = [turn.body for turn in model.contexts[-1].history]
    assert "Quero falar com uma pessoa." in history and first.body in history
    assert "Ainda aguardando" in history
    assert service.handle(inbound, deadline=ExecutionDeadline.start()) == reply
    assert len(model.contexts) == 2
    assert store.list_active_handoffs() == []
    assert (
        responder(store, model).handle(
            message("suppressed-2", "changed"), deadline=ExecutionDeadline.start()
        )
        is None
    )
    assert len(model.contexts) == 2
    assert (
        store.get_generation(provider="test-provider", provider_message_id="suppressed-2").state
        is GenerationState.SUPPRESSED
    )


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ("Quero falar com uma pessoa.", "explicit_human_request"),
        ("Meu couro cabeludo está ardendo.", "personalized_technical_risk"),
        ("Meu cabelo caiu.", "alleged_damage"),
        ("Vou processar vocês.", "legal_threat"),
        ("Quero reclamar.", "relevant_complaint"),
        ("Fui cobrada duas vezes.", "payment_problem"),
    ],
)
@pytest.mark.parametrize("model_handoff", [False, True])
def test_current_trusted_condition_overrides_the_model_and_survives_restart(
    tmp_path, body, reason, model_handoff
):
    from rj_studio_ai.persistence import GenerationState, SqliteConversationStore

    path = tmp_path / "mandatory.db"
    store = SqliteConversationStore(path)
    store.initialize()
    model = AdvisoryModel(
        proposal(
            handoff=model_handoff, handoff_reason="untrusted reason" if model_handoff else None
        )
    )
    reply = responder(store, model).handle(
        message("risk-1", body), deadline=ExecutionDeadline.start()
    )
    assert "equipe" in reply.body
    handoff = store.list_active_handoffs()[0]
    assert handoff.reason_code == reason
    reopened = SqliteConversationStore(path)
    assert reopened.list_active_handoffs() == [handoff]
    assert (
        responder(reopened, model).handle(
            message("risk-2", "Oi"), deadline=ExecutionDeadline.start()
        )
        is None
    )
    assert len(model.contexts) == 1
    assert (
        reopened.get_generation(provider="test-provider", provider_message_id="risk-2").state
        is GenerationState.SUPPRESSED
    )


@pytest.mark.parametrize(
    "reason",
    ["explicit_human_request", "personalized_technical_risk", "requires_human_consultation"],
)
def test_a_familiar_model_reason_is_not_itself_policy_evidence(reason):
    result = finalize_reply(
        proposal(handoff_reason=reason),
        customer_message="Bom dia",
        context=ConversationContext((), ()),
    )
    assert not result.handoff and result.handoff_reason is None


@pytest.mark.parametrize("part_kind", ["declaration", "fact", "critical_claim"])
def test_invalid_model_reference_still_requires_fail_closed_review(part_kind):
    fields = {"knowledge_refs": ["missing-fact"]}
    if part_kind == "fact":
        fields["reply_parts"] = [{"kind": "fact", "knowledge_ref": "missing-fact"}]
    if part_kind == "critical_claim":
        fields["critical_claims"] = [
            {"fact_type": "price", "value": "R$ 1,00", "knowledge_ref": "missing-fact"}
        ]
    result = finalize_reply(
        proposal(handoff=False, handoff_reason=None, **fields),
        customer_message="Qual preço?",
        context=ConversationContext((), ()),
    )
    assert result.handoff and result.handoff_reason == "unavailable_knowledge"
    assert result.knowledge_refs == () and "R$" not in result.reply_text


@pytest.mark.parametrize(
    ("fact", "reason"),
    [
        (
            {"category": "service", "requires_human_consultation": True},
            "requires_human_consultation",
        ),
        ({"category": "handoff_condition"}, "approved_handoff_condition"),
    ],
)
def test_approved_knowledge_conditions_remain_mandatory(fact, reason):
    from datetime import date

    from rj_studio_ai.salon_knowledge import SalonKnowledgeFact

    approved = SalonKnowledgeFact.model_validate(
        {
            "id": "approved-condition",
            "topic": "synthetic",
            "status": "approved",
            "fact_type": "operational_commercial",
            "statement": "Synthetic condition.",
            "approved_by": "synthetic operator",
            "reviewed_at": date(2026, 10, 2),
            "source": "synthetic fixture",
            **fact,
        }
    )
    result = finalize_reply(
        proposal(handoff=False, handoff_reason=None),
        customer_message="Quero informações",
        context=ConversationContext((), (approved,)),
    )
    assert result.handoff and result.handoff_reason == reason
