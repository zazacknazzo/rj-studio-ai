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
    sqlite_busy_timeout_seconds: float = Field(default=5.0, gt=0)
    app_process_count: int = Field(default=1, ge=1)
    salon_knowledge_path: Path = Path("knowledge/rj_studio.yaml")
    automatic_reply: str = "Olá! Recebemos sua mensagem e retornaremos em breve. ✨"
    message_retention_days: int = Field(default=90, ge=1)
    twilio_auth_token: str = ""
    twilio_validate_signature: bool = True
    twilio_public_webhook_url: str | None = None
    twilio_status_callback_url: str | None = None
    twilio_account_sid: str = ""
    twilio_api_key_sid: str = ""
    twilio_api_key_secret: str = ""
    delivery_mode: Literal["legacy", "proactive"] = "legacy"
    outbound_request_timeout_seconds: float = Field(default=5.0, gt=0, lt=30)
    outbound_poll_interval_seconds: float = Field(default=0.25, gt=0)
    outbound_concurrency: int = Field(default=1, ge=1, le=4)
    outbound_maximum_attempts: int = Field(default=3, ge=1, le=10)
    outbound_retry_backoff_base_seconds: float = Field(default=1.0, gt=0)
    outbound_retry_backoff_maximum_seconds: float = Field(default=30.0, gt=0)
    llm_provider: Literal["fixed", "anthropic"] = "fixed"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    anthropic_max_output_tokens: int = Field(default=200, ge=1, le=200)
    conversation_context_maximum_messages: int = Field(default=12, ge=1)
    conversation_context_history_token_budget: int = Field(default=2_000, ge=1)
    llm_input_token_budget: int = Field(default=4_000, ge=1)
    conversation_context_maximum_age_days: int = Field(default=30, ge=1)
    anthropic_input_microusd_per_million: int | None = Field(default=None, ge=0)
    anthropic_output_microusd_per_million: int | None = Field(default=None, ge=0)
