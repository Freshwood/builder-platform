"""Compact the message history before every model request (token budget, ADR-0006).

Without this, every request resends every design the model ever wrote, the material catalog
and example designs from all earlier turns. The model only needs:

- earlier turns: what was asked, which tools ran and what came out, but not the bulky
  arguments (designs) or lookups (catalog, template designs); it can fetch them again;
- the current turn: everything, except designs that a later attempt has superseded (their
  engine errors stay, so the model still sees what it already fixed).

Pydantic AI keeps the processed history for the rest of the run, so superseded designs are
stubbed in the stored model/UI messages too. Provenance does not suffer: every submitted
design is stored in full in ``agent_runs.design_attempts``.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelRequestPart,
    ModelResponse,
    ModelResponsePart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

# design_project / redesign_project: tool names before prompt 2026-10-07.3 (stored chats).
DESIGN_TOOLS = frozenset({"save_design", "design_project", "redesign_project"})
# Read-only lookups whose result can simply be requested again.
LOOKUP_TOOLS = frozenset(
    {"list_materials", "get_template_design", "get_current_design", "list_construction_packs"}
)
DESIGN_STUB = "[gekürzt: früherer Entwurf, aktueller Stand über get_current_design]"
SUPERSEDED_STUB = "[gekürzt: durch einen späteren Entwurf ersetzt]"
LOOKUP_STUB = "[gekürzt: Ergebnis einer früheren Abfrage, bei Bedarf erneut aufrufen]"


def _turn_start(messages: list[ModelMessage]) -> int:
    """Index of the request with the latest user prompt (start of the current turn)."""
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, ModelRequest) and any(
            isinstance(p, UserPromptPart) for p in message.parts
        ):
            return index
    return 0


def _stub_design_call(part: ToolCallPart, stub: str) -> ToolCallPart:
    args = part.args_as_dict()
    kept: dict[str, Any] = {k: v for k, v in args.items() if k in ("title", "new_project")}
    return replace(part, args={**kept, "design": stub})


def _compact_response(
    message: ModelResponse, *, earlier: bool, keep_call_id: str | None
) -> ModelResponse:
    parts: list[ModelResponsePart] = []
    for part in message.parts:
        if earlier and isinstance(part, ThinkingPart):
            continue
        if (
            isinstance(part, ToolCallPart)
            and part.tool_name in DESIGN_TOOLS
            and part.tool_call_id != keep_call_id
        ):
            part = _stub_design_call(part, DESIGN_STUB if earlier else SUPERSEDED_STUB)
        parts.append(part)
    return replace(message, parts=parts)


def _compact_request(message: ModelRequest) -> ModelRequest:
    parts: list[ModelRequestPart] = [
        replace(p, content=LOOKUP_STUB)
        if isinstance(p, ToolReturnPart) and p.tool_name in LOOKUP_TOOLS
        else p
        for p in message.parts
    ]
    return replace(message, parts=parts)


def _last_design_call(messages: list[ModelMessage]) -> str | None:
    for message in reversed(messages):
        if isinstance(message, ModelResponse):
            for part in reversed(message.parts):
                if isinstance(part, ToolCallPart) and part.tool_name in DESIGN_TOOLS:
                    return part.tool_call_id
    return None


def compact_history(messages: list[ModelMessage]) -> list[ModelMessage]:
    start = _turn_start(messages)
    keep = _last_design_call(messages[start:])
    out: list[ModelMessage] = []
    for index, message in enumerate(messages):
        earlier = index < start
        if isinstance(message, ModelResponse):
            out.append(_compact_response(message, earlier=earlier, keep_call_id=keep))
        elif earlier:
            out.append(_compact_request(message))
        else:
            out.append(message)
    return out


async def process_history(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Async wrapper: a sync processor would be run in a thread pool on every request."""
    return compact_history(messages)
