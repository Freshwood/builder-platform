"""Application settings from environment variables (12-factor)."""

from __future__ import annotations

from functools import cache
from typing import Annotated, Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEV_SECRET = "dev-only-insecure-session-secret"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://homeworking:homeworking@localhost:5433/homeworking"
    session_secret: SecretStr = SecretStr(DEV_SECRET)
    # Comma-separated in the environment (CORS_ORIGINS=http://a,http://b), not JSON.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    # Create tables on startup instead of running Alembic (SQLite dev / E2E only).
    auto_create_schema: bool = False

    llm_mode: Literal["test", "openai"] = "test"
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = ""
    llm_api_key: SecretStr | None = None
    agent_request_limit: int = 8
    agent_total_tokens_limit: int = 60_000

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _check_production(self) -> Settings:
        if self.environment == "production":
            if self.session_secret.get_secret_value() == DEV_SECRET:
                raise ValueError("SESSION_SECRET must be set in production")
            if self.llm_mode == "test":
                raise ValueError("LLM_MODE=test is not allowed in production")
        if self.llm_mode == "openai" and not self.llm_model:
            raise ValueError("LLM_MODEL is required when LLM_MODE=openai")
        return self

    @property
    def secure_cookies(self) -> bool:
        return self.environment == "production"


@cache
def get_settings() -> Settings:
    return Settings()
