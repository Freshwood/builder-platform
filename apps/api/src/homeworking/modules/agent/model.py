"""LLM model factory (ADR-0003, ADR-0006): offline test model or OpenAI-compatible endpoints."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from homeworking.modules.agent.offline import offline_model
from homeworking.modules.agent.routing import Role
from homeworking.settings import Settings


@dataclass(frozen=True)
class Models:
    """One model per role; ``fast`` falls back to the designer on provider errors."""

    designer: Model
    fast: Model

    def for_role(self, role: Role) -> Model:
        return self.designer if role == "designer" else self.fast

    @property
    def routed(self) -> bool:
        return self.fast is not self.designer


def build_model(settings: Settings, name: str | None = None) -> Model:
    if settings.llm_mode == "test":
        return offline_model()
    name = name or settings.llm_model
    # The openai SDK takes seconds to import; only pay for it when it is actually used.
    from pydantic_ai.providers.openai import OpenAIProvider

    api_key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
    provider = OpenAIProvider(base_url=settings.llm_base_url, api_key=api_key)
    if "openrouter.ai" in settings.llm_base_url:
        from pydantic_ai.models.openrouter import (
            OpenRouterModel,
            OpenRouterModelSettings,
            OpenRouterReasoning,
        )

        # Without an explicit reasoning request some models (e.g. Solar) write their thinking
        # into the answer text and stop without calling a tool.
        reasoning: OpenRouterReasoning = (
            {"enabled": False}
            if settings.llm_reasoning == "off"
            else {"effort": settings.llm_reasoning}
        )
        return OpenRouterModel(
            name,
            provider=provider,
            settings=OpenRouterModelSettings(
                max_tokens=settings.llm_max_output_tokens,
                temperature=settings.llm_temperature,
                openrouter_reasoning=reasoning,
                # Explicit cache points for providers that need them (Anthropic, Gemini); the
                # static prefix (instructions + tools) is ~70-95 % of every request (ADR-0006).
                # OpenAI-style providers cache automatically and ignore these flags.
                openrouter_cache_instructions=True,
                openrouter_cache_tool_definitions=True,
                openrouter_cache_messages=True,
            ),
        )
    from pydantic_ai.models.openai import OpenAIChatModel

    return OpenAIChatModel(
        name,
        provider=provider,
        settings=ModelSettings(
            max_tokens=settings.llm_max_output_tokens, temperature=settings.llm_temperature
        ),
    )


def build_models(settings: Settings) -> Models:
    designer = build_model(settings)
    if settings.llm_mode == "test" or not settings.llm_model_fast:
        return Models(designer=designer, fast=designer)
    from pydantic_ai.models.fallback import FallbackModel

    fast = build_model(settings, settings.llm_model_fast)
    return Models(designer=designer, fast=FallbackModel(fast, designer))
