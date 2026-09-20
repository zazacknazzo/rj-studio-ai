"""Provider-neutral institutional voice for Lívia, the RJ Studio AI Attendant."""

import re
import unicodedata
from dataclasses import dataclass


class PersonaValidationError(ValueError):
    """A reply violates Lívia's deterministic response-surface limits."""


@dataclass(frozen=True, slots=True)
class LiviaPersona:
    name: str = "Lívia"
    institution: str = "RJ Studio"

    @property
    def instructions(self) -> str:
        return (
            "Você é Lívia, a atendente virtual do RJ Studio. Escreva em português brasileiro "
            "natural, gentil, segura, objetiva e conversacional. Adapte levemente formalidade, "
            "concisão e vocabulário ao Customer sem imitar erros, agressividade ou gírias. "
            "Apresente-se apenas quando fizer sentido; não reinicie uma Conversation já em curso. "
            "Se perguntarem explicitamente se você é IA, robô ou pessoa, responda com "
            "transparência que é atendente virtual. Não afirme ser humana, ter experiências "
            "pessoais, corpo ou vida pessoal. Prefira uma pergunta clara por vez. Evite call "
            "center, marketing genérico, exclamações, listas e emojis em excesso. Não use tom "
            "confiante para esconder incerteza."
        )

    def validate_reply(self, customer_message: str, reply_text: str) -> None:
        if len(reply_text) > 800:
            raise PersonaValidationError("reply exceeds persona length limit")
        if len(_paragraphs(reply_text)) > 3:
            raise PersonaValidationError("reply exceeds persona paragraph limit")
        if _emoji_count(reply_text) > 1:
            raise PersonaValidationError("reply exceeds persona emoji limit")
        normalized_reply = _normalize(reply_text)
        if "ola! como posso ajuda-lo hoje?" in normalized_reply:
            raise PersonaValidationError("reply uses prohibited call-center wording")
        if any(
            phrase in normalized_reply
            for phrase in (
                "sou humana",
                "sou uma pessoa",
                "minha experiencia pessoal",
                "ja tive essa experiencia",
            )
        ):
            raise PersonaValidationError("reply misrepresents Lívia's identity")
        if _asks_about_identity(customer_message) and not any(
            phrase in normalized_reply
            for phrase in (
                "atendente virtual",
                "assistente virtual",
                "inteligencia artificial",
                "sou uma ia",
            )
        ):
            raise PersonaValidationError("identity question requires transparency")


def _paragraphs(text: str) -> list[str]:
    return [paragraph for paragraph in re.split(r"\n\s*\n", text.strip()) if paragraph]


def _emoji_count(text: str) -> int:
    return sum(1 for character in text if unicodedata.category(character) == "So")


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _asks_about_identity(customer_message: str) -> bool:
    normalized = _normalize(customer_message)
    return any(phrase in normalized for phrase in ("e uma ia", "e ia", "e robo", "uma pessoa"))
