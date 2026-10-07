"""Offline token metering: what the agent would send to an LLM per model request.

Counts characters of the parts an OpenAI-compatible chat request carries (instructions, tool
definitions, message history) and of the model output. Tokens are estimated with a fixed
chars-per-token ratio so that measurements are deterministic, need no network and stay
comparable across prompt versions. Absolute numbers are approximations; deltas are exact.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo
from pydantic_ai.tools import ToolDefinition

# German prose and JSON average roughly 3.2 characters per token with current BPE tokenizers
# (o200k / Gemini / Solar measured on this repo's prompts). Used uniformly for all scenarios.
CHARS_PER_TOKEN = 3.2


def tokens(chars: int) -> int:
    return round(chars / CHARS_PER_TOKEN)


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def tool_definitions_json(tools: Sequence[ToolDefinition]) -> str:
    """Tool definitions as the provider receives them (name, description, JSON schema)."""
    return _compact(
        [
            {"name": t.name, "description": t.description, "parameters": t.parameters_json_schema}
            for t in tools
        ]
    )


def prefix_fingerprint(info: AgentInfo) -> str:
    """Hash of the static request prefix; must not change between requests (prompt caching)."""
    prefix = (info.instructions or "") + tool_definitions_json(info.function_tools)
    return hashlib.sha256(prefix.encode()).hexdigest()[:16]


def part_chars(part: Any) -> int:
    if isinstance(part, UserPromptPart | SystemPromptPart):
        return len(part.content) if isinstance(part.content, str) else len(_compact(part.content))
    if isinstance(part, ToolCallPart):
        return len(part.tool_name) + len(part.args_as_json_str())
    if isinstance(part, ToolReturnPart):
        return len(part.model_response_str())
    if isinstance(part, RetryPromptPart):
        return len(part.model_response())
    if isinstance(part, TextPart | ThinkingPart):
        return len(part.content)
    return 0


def messages_chars(messages: Sequence[ModelMessage]) -> int:
    return sum(part_chars(p) for m in messages for p in m.parts)


@dataclass(frozen=True)
class RequestSize:
    instructions: int
    tools: int
    history: int
    output: int
    fingerprint: str

    @property
    def prefix(self) -> int:
        return self.instructions + self.tools

    @property
    def input(self) -> int:
        return self.prefix + self.history


@dataclass
class Meter:
    """Records the size of every model request made through ``wrap``-ped model functions."""

    requests: list[RequestSize] = field(default_factory=list)

    def wrap(
        self, respond: Callable[[list[ModelMessage], AgentInfo], ModelResponse]
    ) -> Callable[[list[ModelMessage], AgentInfo], ModelResponse]:
        def recording(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            response = respond(messages, info)
            self.requests.append(
                RequestSize(
                    instructions=len(info.instructions or ""),
                    tools=len(tool_definitions_json(info.function_tools)),
                    history=messages_chars(messages),
                    output=messages_chars([response]),
                    fingerprint=prefix_fingerprint(info),
                )
            )
            return response

        return recording

    def totals(self) -> dict[str, Any]:
        input_chars = sum(r.input for r in self.requests)
        output_chars = sum(r.output for r in self.requests)
        prefix_chars = sum(r.prefix for r in self.requests)
        return {
            "requests": len(self.requests),
            "prefix_tokens_per_request": tokens(self.requests[0].prefix) if self.requests else 0,
            "input_tokens": tokens(input_chars),
            "output_tokens": tokens(output_chars),
            "prefix_share": round(prefix_chars / input_chars, 3) if input_chars else 0.0,
            "max_request_input_tokens": max((tokens(r.input) for r in self.requests), default=0),
            "stable_prefix": len({r.fingerprint for r in self.requests}) <= 1,
            "per_request": [
                {k: v for k, v in asdict(r).items() if k != "fingerprint"} for r in self.requests
            ],
        }
