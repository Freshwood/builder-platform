"""Application settings from environment variables (12-factor)."""

from __future__ import annotations

from functools import cache
from typing import Annotated, Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEV_SECRET = "dev-only-insecure-session-secret"  # noqa: S105
# Environments in which the known development secret and the offline model are acceptable.
LOCAL_ENVIRONMENTS = ("development", "test")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Production unless said otherwise: a deployment that forgets ENVIRONMENT must fail on the
    # development secret and the offline model, not run with them. ``.env.example`` sets
    # ``development``; the test suite sets ``test``.
    environment: Literal["development", "test", "production"] = "production"
    database_url: str = "postgresql+psycopg://homeworking:homeworking@localhost:5433/homeworking"
    session_secret: SecretStr = SecretStr(DEV_SECRET)
    # Comma-separated in the environment (CORS_ORIGINS=http://a,http://b), not JSON.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    # Create tables on startup instead of running Alembic (SQLite dev / E2E only).
    auto_create_schema: bool = False

    llm_mode: Literal["test", "openai"] = "test"
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = ""
    # Optional cheaper/faster model for simple turns (templates, parameter changes, questions);
    # free designs stay on llm_model (ADR-0006). Empty = llm_model for everything.
    llm_model_fast: str = ""
    llm_api_key: SecretStr | None = None
    # Reasoning effort for OpenRouter models; keeps the model's thinking out of the answer text.
    llm_reasoning: Literal["off", "minimal", "low", "medium", "high"] = "low"
    # Output cap per model request: a complete design plus explanation needs ~6K tokens.
    llm_max_output_tokens: int = 12_000
    # OpenRouter picks the provider by this criterion; "throughput" prefers the one with the most
    # tokens per second (the time of a design is output tokens / speed). Empty = OpenRouter default.
    # Building blocks (calc_engine/pipeline/blocks): the engine builds modules for houses, shelves,
    # tables, podiums, pergolas and fences. "auto" also puts a block into a single-module skeleton
    # whose brief clearly names such an object; "model" only builds what the skeleton asked for.
    engine_blocks: Literal["auto", "model"] = "auto"
    llm_provider_sort: Literal["", "price", "throughput", "latency"] = "throughput"
    # The pipeline stages (ADR-0010) fill a schema; thinking only costs time and tokens. A live
    # run with ``llm_reasoning=low`` spent 8-17K output tokens on a skeleton and 14-24K on the
    # modules of one design, mostly reasoning, and hit the 12K cap.
    # The chat model's turn that starts a project only fills the brief of ``plan_design``; with the
    # default ``llm_reasoning`` it took 30-70 s (and sometimes ran into the token limit), with
    # thinking off 8-15 s. Later turns (changes, questions) keep ``llm_reasoning``.
    llm_plan_reasoning: Literal["off", "minimal", "low", "medium", "high"] = "off"
    llm_stage_reasoning: Literal["off", "minimal", "low", "medium", "high"] = "off"
    # The module stage places parts in 3D; it is the only stage where thinking pays off.
    llm_module_reasoning: Literal["off", "minimal", "low", "medium", "high"] = "minimal"
    llm_stage_max_output_tokens: int = 16_000
    # Enforce the time budget of a design (``calc_engine.pipeline.budget``); only tools turn it off.
    design_time_budget: bool = True
    # Low temperature: designs must follow the schema and the user's brief, not be creative.
    llm_temperature: float = 0.2
    # May the chat agent's ``save_design`` create a project? Live, new designs go through the
    # staged pipeline (``plan_design``, ADR-0010) and ``save_design`` only changes the open
    # project. The offline model drafts a design itself and saves it, so unset means: allowed in
    # test mode, refused otherwise (see ``save_design_creates``).
    agent_save_design_creates: bool | None = None
    # Free-form designs need a few repair rounds and long tool arguments (ADR-0004).
    agent_request_limit: int = 12
    # Counts input (incl. cached) and output of all requests of a turn; reasoning models used
    # 200K in seven requests of a kids' podium design (run 3289388f).
    agent_total_tokens_limit: int = 1_000_000

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _check_environment(self) -> Settings:
        if self.environment not in LOCAL_ENVIRONMENTS:
            if self.session_secret.get_secret_value() == DEV_SECRET:
                raise ValueError(
                    f"SESSION_SECRET must be set when ENVIRONMENT={self.environment} "
                    "(ENVIRONMENT defaults to production; use development or test locally)"
                )
            if self.llm_mode == "test":
                raise ValueError(
                    f"LLM_MODE=test is not allowed when ENVIRONMENT={self.environment}"
                )
        if self.llm_mode == "openai" and not self.llm_model:
            raise ValueError("LLM_MODEL is required when LLM_MODE=openai")
        return self

    @property
    def save_design_creates(self) -> bool:
        """``agent_save_design_creates``, by default derived from the model mode."""
        if self.agent_save_design_creates is not None:
            return self.agent_save_design_creates
        return self.llm_mode == "test"

    @property
    def secure_cookies(self) -> bool:
        return self.environment == "production"


@cache
def get_settings() -> Settings:
    return Settings()
