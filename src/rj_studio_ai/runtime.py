"""Shared local composition for the configured reply generator."""

from rj_studio_ai.config import Settings
from rj_studio_ai.generation import FixedReplyGenerator, ReplyGenerator
from rj_studio_ai.providers.anthropic import AnthropicReplyGenerator, LLMPriceTable


def generator_from_settings(settings: Settings) -> ReplyGenerator:
    if settings.llm_provider == "fixed":
        return FixedReplyGenerator(settings.automatic_reply)
    pricing = None
    if (
        settings.anthropic_input_microusd_per_million is not None
        and settings.anthropic_output_microusd_per_million is not None
    ):
        pricing = LLMPriceTable(
            input_microusd_per_million=settings.anthropic_input_microusd_per_million,
            output_microusd_per_million=settings.anthropic_output_microusd_per_million,
        )
    return AnthropicReplyGenerator(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
        max_output_tokens=settings.anthropic_max_output_tokens,
        pricing=pricing,
    )
