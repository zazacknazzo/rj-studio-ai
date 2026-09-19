from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "RJ Studio AI"
    database_path: Path = Path("data/rj_studio_ai.db")
    automatic_reply: str = "Olá! Recebemos sua mensagem e retornaremos em breve. ✨"
    message_retention_days: int = Field(default=90, ge=1)
    twilio_auth_token: str = ""
    twilio_validate_signature: bool = True
    twilio_public_webhook_url: str | None = None
    llm_provider: Literal["fixed", "anthropic"] = "fixed"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    anthropic_max_output_tokens: int = Field(default=240, ge=1)
    anthropic_input_microusd_per_million: int | None = Field(default=None, ge=0)
    anthropic_output_microusd_per_million: int | None = Field(default=None, ge=0)
