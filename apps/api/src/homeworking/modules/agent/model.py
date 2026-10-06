"""LLM model factory (ADR-0003): offline test model or any OpenAI-compatible endpoint."""

from __future__ import annotations

from pydantic_ai.models import Model

from homeworking.modules.agent.offline import offline_model
from homeworking.settings import Settings


def build_model(settings: Settings) -> Model:
    if settings.llm_mode == "test":
        return offline_model()
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
            settings.llm_model,
            provider=provider,
            settings=OpenRouterModelSettings(openrouter_reasoning=reasoning),
        )
    from pydantic_ai.models.openai import OpenAIChatModel

    return OpenAIChatModel(settings.llm_model, provider=provider)
