"""LLM model factory (ADR-0003, ADR-0006): offline test model or OpenAI-compatible endpoints.

The offline model belongs to the chat agent (it speaks the agent's tools); the factory does not
know it. The composition root passes it in as ``offline`` and only imports it in test mode.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from homeworking.settings import Settings

Effort = Literal["off", "minimal", "low", "medium", "high"]
# Which model a task needs: free-form designs and skeletons need the larger one (ADR-0006).
Role = Literal["designer", "fast"]
# Builds the offline model of ``LLM_MODE=test``.
OfflineFactory = Callable[[], Model]


@dataclass(frozen=True)
class Models:
    """One model per role; ``fast`` falls back to the designer on provider errors."""

    designer: Model
    fast: Model
    # Pipeline stages only: the module stage may think more than the other stages (geometry).
    modules: Model | None = None

    @property
    def module_stage(self) -> Model:
        return self.modules or self.fast

    def for_role(self, role: Role) -> Model:
        return self.designer if role == "designer" else self.fast

    @property
    def routed(self) -> bool:
        return self.fast is not self.designer


def build_model(
    settings: Settings,
    name: str | None = None,
    *,
    reasoning_effort: Effort | None = None,
    max_tokens: int | None = None,
    offline: OfflineFactory | None = None,
) -> Model:
    if settings.llm_mode == "test":
        if offline is None:
            raise ValueError("LLM_MODE=test needs an offline model factory")
        return offline()
    name = name or settings.llm_model
    effort = reasoning_effort or settings.llm_reasoning
    max_tokens = max_tokens or settings.llm_max_output_tokens
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
            {"enabled": False} if effort == "off" else {"effort": effort}
        )
        return OpenRouterModel(
            name,
            provider=provider,
            settings=OpenRouterModelSettings(
                max_tokens=max_tokens,
                temperature=settings.llm_temperature,
                openrouter_reasoning=reasoning,
                **(
                    {"openrouter_provider": {"sort": settings.llm_provider_sort}}
                    if settings.llm_provider_sort
                    else {}
                ),
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
        settings=ModelSettings(max_tokens=max_tokens, temperature=settings.llm_temperature),
    )


def reasoning_settings(settings: Settings, effort: Effort) -> ModelSettings | None:
    """Per-run model settings that set the reasoning effort, or ``None`` where the provider has no
    such setting (offline model, plain OpenAI-compatible endpoint)."""
    if settings.llm_mode == "test" or "openrouter.ai" not in settings.llm_base_url:
        return None
    from pydantic_ai.models.openrouter import OpenRouterModelSettings

    reasoning = {"enabled": False} if effort == "off" else {"effort": effort}
    return OpenRouterModelSettings(openrouter_reasoning=reasoning)  # type: ignore[typeddict-item]


def build_models(
    settings: Settings, *, stages: bool = False, offline: OfflineFactory | None = None
) -> Models:
    """The chat models, or with ``stages`` the same models set up for the pipeline stages: little
    reasoning and a higher output cap (structured output, no conversation)."""
    options: dict[str, Any] = (
        {
            "reasoning_effort": settings.llm_stage_reasoning,
            "max_tokens": settings.llm_stage_max_output_tokens,
        }
        if stages
        else {}
    )
    designer = build_model(settings, offline=offline, **options)
    if settings.llm_mode == "test":
        return Models(designer=designer, fast=designer)
    from pydantic_ai.models.fallback import FallbackModel

    fast_name = settings.llm_model_fast or None
    fast = build_model(settings, fast_name, **options) if fast_name else designer
    modules: Model | None = None
    if stages and settings.llm_module_reasoning != settings.llm_stage_reasoning:
        modules = build_model(
            settings,
            fast_name,
            reasoning_effort=settings.llm_module_reasoning,
            max_tokens=settings.llm_stage_max_output_tokens,
        )
    if not fast_name:
        return Models(designer=designer, fast=designer, modules=modules)
    return Models(
        designer=designer,
        fast=FallbackModel(fast, designer),
        modules=FallbackModel(modules, designer) if modules else None,
    )
