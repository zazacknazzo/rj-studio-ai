from pathlib import Path

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
    twilio_auth_token: str = ""
    twilio_validate_signature: bool = True
    twilio_public_webhook_url: str | None = None
