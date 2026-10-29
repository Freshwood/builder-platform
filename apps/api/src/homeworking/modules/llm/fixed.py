"""A model that answers with a fixed text: safety referrals never reach a real LLM."""

from __future__ import annotations

from collections.abc import AsyncIterator

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel


def fixed_text_model(text: str) -> FunctionModel:
    """Model that always answers with ``text`` (used for safety referrals)."""

    def respond(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(text)])

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[str]:
        yield text

    return FunctionModel(respond, stream_function=stream, model_name="homeworking-safety")
