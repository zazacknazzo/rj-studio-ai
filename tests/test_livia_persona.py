import pytest

from rj_studio_ai.livia_persona import LiviaPersona, PersonaValidationError


def test_persona_is_small_and_separate_from_salon_facts() -> None:
    persona = LiviaPersona()
    assert len(persona.instructions) < 1_500
    for forbidden in ("R$", "horário", "disponibilidade", "serviço"):
        assert forbidden not in persona.instructions.casefold()


@pytest.mark.parametrize(
    "question",
    ["Você é uma IA?", "Estou falando com uma pessoa?", "Você é robô?"],
)
def test_explicit_identity_question_requires_transparency(question: str) -> None:
    with pytest.raises(PersonaValidationError, match="transparency"):
        LiviaPersona().validate_reply(question, "Sou a Lívia, posso ajudar!")
    LiviaPersona().validate_reply(question, "Sou a Lívia, atendente virtual do RJ Studio. 😊")


def test_persona_rejects_surface_violations() -> None:
    persona = LiviaPersona()
    for reply in (
        "x" * 801,
        "A\n\nB\n\nC\n\nD",
        "Oi 😊✨",
        "Olá! Como posso ajudá-lo hoje?",
        "Sou humana e já tive essa experiência.",
    ):
        with pytest.raises(PersonaValidationError):
            persona.validate_reply("Oi", reply)


def test_persona_allows_a_short_natural_reply() -> None:
    LiviaPersona().validate_reply("Oi", "Oi! Sou a Lívia, do RJ Studio 😊 Como posso ajudar?")
