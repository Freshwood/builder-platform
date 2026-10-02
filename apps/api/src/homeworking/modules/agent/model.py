"""LLM model factory (ADR-0003): offline test model or any OpenAI-compatible endpoint."""

from __future__ import annotations

from pydantic_ai.models import Model

from homeworking.modules.agent.offline import offline_model
from homeworking.settings import Settings


def build_model(settings: Settings) -> Model:
    if settings.llm_mode == "test":
        return offline_model()
    # The openai SDK takes seconds to import; only pay for it when it is actually used.
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    api_key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
    provider = OpenAIProvider(base_url=settings.llm_base_url, api_key=api_key)
    return OpenAIChatModel(settings.llm_model, provider=provider)
