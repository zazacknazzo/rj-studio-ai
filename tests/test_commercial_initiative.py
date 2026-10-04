"""Planning stays model-owned; product signals never authorize facts or effects."""

import pytest
from test_commercial_steering import captured_trace, part, price_context, proposal

from rj_studio_ai.conversation_context import ConversationContext
from rj_studio_ai.grounding import finalize_reply


def test_answer_only_has_a_soft_early_closure_signal_without_safety_failure():
    trace, result = captured_trace(
        proposal(
            {"kind": "fact", "knowledge_ref": "price-corte"},
            knowledge_refs=["price-corte"],
            next_action="answer_only",
        ),
        customer="Quanto custa o corte?",
        context=price_context(),
    )
    assert result.reply_text == "O corte custa R$ 120,00."
    assert not result.handoff
    assert not trace.commercial_continuation_present
    assert trace.conversation_closed_early is True


@pytest.mark.parametrize(
    "text",
    [
        "Quer ajuda para pensar no próximo passo?",
        "Podemos conversar um pouco sobre o que você procura?",
    ],
)
def test_commercial_continuation_has_free_wording_and_no_operational_action(text):
    trace, result = captured_trace(
        proposal(
            {"kind": "fact", "knowledge_ref": "price-corte"},
            part(text, purpose="commercial_continuation", information_targets=[]),
            knowledge_refs=["price-corte"],
            next_action="continue_conversation",
        ),
        customer="Quanto custa o corte?",
        context=price_context(),
    )
    assert result.reply_text == "O corte custa R$ 120,00. " + text
    assert trace.commercial_continuation_present
    assert trace.conversation_closed_early is False
    assert trace.authorized_actions == ()
    assert not result.handoff


def test_social_reply_is_not_forced_into_commercial_continuation():
    trace, result = captured_trace(
        proposal(
            part("Que bom conversar com você!", purpose="social", information_targets=[]),
            intents=["greeting"],
            next_action="social_response",
        ),
        customer="Oi!",
        context=ConversationContext((), ()),
    )
    assert result.reply_text == "Que bom conversar com você!"
    assert not trace.commercial_continuation_present
    assert trace.conversation_closed_early is None


def test_safety_context_does_not_render_a_proposed_commercial_continuation():
    result = finalize_reply(
        proposal(
            part(
                "Quer continuar conversando?",
                purpose="commercial_continuation",
                information_targets=[],
            ),
            intents=["technical_guidance"],
            next_action="continue_conversation",
        ),
        customer_message="Meu couro cabeludo está ardendo após a química.",
        context=ConversationContext((), ()),
    )
    assert result.handoff
    assert "Quer continuar conversando?" not in result.reply_text


def test_commercial_planning_instruction_preserves_context_and_optional_cta():
    from rj_studio_ai.livia_persona import agentic_surface_instructions

    instructions = agentic_surface_instructions()
    assert "consultiva" in instructions
    assert "apenas a informação" in instructions
    assert "continue_conversation" in instructions
    assert "CTA não é obrigatório" in instructions
    assert "Quanto custa o corte?" not in instructions


def test_advisory_continuation_does_not_start_persisted_intake_or_handoff(tmp_path):
    from test_agentic_intake import send

    from rj_studio_ai.generation import GeneratedReply
    from rj_studio_ai.persistence import SqliteConversationStore

    class Model:
        def is_configured(self):
            return True

        def generate(self, message, *, context, remaining_budget):
            return GeneratedReply(
                decision=proposal(
                    part(
                        "Me conta o que você procura?",
                        purpose="question",
                        information_targets=["customer_goal"],
                    ),
                    intents=["other"],
                    next_action="continue_conversation",
                )
            )

    store = SqliteConversationStore(tmp_path / "conversation.db")
    store.initialize()
    reply, intake = send(store, Model(), "Quero conversar")
    assert reply.body == "Me conta o que você procura?"
    assert intake is None
    assert not store.list_active_handoffs()


def test_advisory_continuation_cannot_authorize_availability():
    result = finalize_reply(
        proposal(
            part("Temos vaga amanhã.", purpose="commercial_continuation", information_targets=[]),
            next_action="continue_conversation",
        ),
        customer_message="Quanto custa?",
        context=ConversationContext((), ()),
    )
    assert result.handoff
    assert "Temos vaga amanhã." not in result.reply_text
