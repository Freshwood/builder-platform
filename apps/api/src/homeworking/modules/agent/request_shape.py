"""Shape of the model request that was sent, without any text (diagnosis of provider errors).

A provider can reject a request for its structure ("Missing required parameter:
'messages[6].content'") although every earlier request of the run was fine. For a failed run
nothing else survives (``agent_runs.model_messages`` is ``NULL``), so the capability
``RecordRequestShape`` (``tools.py``) keeps the shape of the latest request in ``AgentDeps`` and
``api/chat.py`` stores it with the failed run (``usage["failed_request"]``).

Only structure is recorded: message and part kinds, tool names, shortened tool call ids, lengths
in characters and emptiness flags. Never user text, model text, tool arguments or tool output.

Two views are kept, because the indices differ:

- ``messages``: the pydantic-ai history as sent (after history processing and the framework's
  clean-up that merges consecutive requests).
- ``provider.messages``: the OpenAI-style array the provider received. Instructions become the
  leading system messages, a response without parts vanishes and a request with several tool
  returns becomes several ``tool`` messages. This view comes from the model's private
  ``_map_messages`` (pydantic-ai 2.49); if that internal is missing or fails, the view is
  ``{"available": false}`` and nothing else breaks.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Sequence
from typing import Any

import pydantic_ai
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    RetryPromptPart,
    ToolReturnPart,
)
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.settings import merge_model_settings

# Bump when the layout of the record changes.
SHAPE_VERSION = 1
# Newest messages kept per view (the rest is only counted); keeps the record under ~20 KB.
KEEP_MESSAGES = 40
# Parts listed per message (a response with many parallel tool calls); the rest is counted.
MAX_PARTS = 12
_ID_KEEP = 8


def short_id(tool_call_id: Any) -> str | None:
    """Last characters of a tool call id (ids can be long; the tail tells them apart)."""
    if not isinstance(tool_call_id, str) or not tool_call_id:
        return None
    return tool_call_id if len(tool_call_id) <= _ID_KEEP + 2 else "…" + tool_call_id[-_ID_KEEP:]


def _chars(content: Any) -> int | None:
    """Length of the text of ``content`` (``None`` for no content at all)."""
    if content is None:
        return None
    if isinstance(content, str):
        return len(content)
    if isinstance(content, Sequence):
        return sum(len(item) for item in content if isinstance(item, str))
    return len(json.dumps(content, default=str))


def _part_chars(part: Any) -> int | None:
    """Characters the part contributes to the request, as the model would see them."""
    try:
        if isinstance(part, ToolReturnPart):
            return len(part.model_response_str())
        if isinstance(part, RetryPromptPart):
            return len(part.model_response())
        if getattr(part, "part_kind", None) == "tool-call":
            return len(part.args_as_json_str())
        return _chars(getattr(part, "content", None))
    except Exception:
        return None


def _part_shape(part: Any) -> dict[str, Any]:
    shape: dict[str, Any] = {"kind": getattr(part, "part_kind", type(part).__name__)}
    if (tool := getattr(part, "tool_name", None)) is not None:
        shape["tool"] = tool
    if (call_id := short_id(getattr(part, "tool_call_id", None))) is not None:
        shape["id"] = call_id
    chars = _part_chars(part)
    shape["chars"] = chars
    if shape["kind"] != "tool-call":
        content = getattr(part, "content", None)
        # Whitespace-only text counts as empty, too (``chars`` stays the real length).
        if chars == 0 or (isinstance(content, str) and not content.strip()):
            shape["empty"] = True
    return shape


def message_shapes(messages: Sequence[ModelMessage]) -> list[dict[str, Any]]:
    """Per message: absolute index, kind and the shape of every part (no text)."""
    shapes: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        parts = list(message.parts)
        entry: dict[str, Any] = {
            "i": index,
            "kind": "response" if isinstance(message, ModelResponse) else "request",
            "parts": [_part_shape(p) for p in parts[:MAX_PARTS]],
        }
        if len(parts) > MAX_PARTS:
            entry["more_parts"] = len(parts) - MAX_PARTS
        if not parts:
            entry["empty"] = True
        shapes.append(entry)
    return shapes


# --------------------------------------------------------------------------------------------
# Provider-level (OpenAI style) array
# --------------------------------------------------------------------------------------------


def _mapped_chars(content: Any) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(
            len(item["text"])
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        )
    return 0


def _mapped_entry(index: int, message: Any) -> dict[str, Any]:
    content = message.get("content")
    return {
        "i": index,
        "role": message.get("role"),
        "has_content": content is not None and content != "" and content != [],
        "chars": _mapped_chars(content),
        "tool_calls": len(message.get("tool_calls") or []),
        "tool_call_id": bool(message.get("tool_call_id")),
    }


def _is_suspicious(entry: dict[str, Any]) -> bool:
    """The pattern behind 'Missing required parameter: messages[i].content'.

    No content and no tool calls, or a tool message without content. An assistant message with
    tool calls and ``content: null`` is valid and not flagged.
    """
    if entry["role"] == "tool":
        return not entry["has_content"]
    return not entry["has_content"] and not entry["tool_calls"]


def mapped_shapes(mapped: Sequence[Any]) -> tuple[list[dict[str, Any]], list[int]]:
    """Entries of the provider array and the indices of the suspicious ones."""
    entries = [_mapped_entry(i, m) for i, m in enumerate(mapped)]
    return entries, [e["i"] for e in entries if _is_suspicious(e)]


def _signature(entry: dict[str, Any]) -> tuple[Any, ...]:
    return (entry["role"], entry["has_content"], entry["tool_calls"], entry["tool_call_id"])


async def _sources(
    model: Any,
    messages: list[ModelMessage],
    params: Any,
    settings: Any,
    mapped: list[dict[str, Any]],
) -> list[int | None] | None:
    """Pydantic-ai message index behind every provider message (``None`` = instructions).

    Maps every message alone (without instructions) and checks that the pieces, with the
    instruction messages inserted after the leading system messages, reproduce the full array.
    Returns ``None`` if they do not (then the relation is unknown rather than wrong).
    """
    alone = dataclasses.replace(params, instruction_parts=[])
    pieces: list[tuple[int, dict[str, Any]]] = []
    for index, message in enumerate(messages):
        for item in await model._map_messages([message], alone, model_settings=settings):
            pieces.append((index, _mapped_entry(0, item)))
    extra = len(mapped) - len(pieces)
    if extra < 0:
        return None
    lead = 0
    while lead < len(pieces) and pieces[lead][1]["role"] == "system":
        lead += 1
    sources: list[int | None] = [i for i, _ in pieces]
    sources[lead:lead] = [None] * extra
    expected = [_signature(e) for _, e in pieces]
    expected[lead:lead] = [_signature(mapped[lead + k]) for k in range(extra)]
    if expected != [_signature(e) for e in mapped]:
        return None
    return sources


def _mapper(model: Any) -> Any | None:
    """The model that can map messages (a wrapper or a fallback chain: the first candidate)."""
    seen = 0
    while model is not None and seen < 5:
        if callable(getattr(model, "_map_messages", None)):
            return model
        inner = getattr(model, "wrapped", None)
        if inner is None:
            candidates = getattr(model, "models", None)
            inner = candidates[0] if candidates else None
        model, seen = inner, seen + 1
    return None


async def _provider_view(request_context: ModelRequestContext) -> dict[str, Any]:
    model = _mapper(request_context.model)
    if model is None:
        return {"available": False, "reason": "no_mapper"}
    try:
        settings = merge_model_settings(
            getattr(model, "settings", None), request_context.model_settings
        )
        params = request_context.model_request_parameters
        messages = list(request_context.messages)
        mapped_raw = await model._map_messages(messages, params, model_settings=settings)
        entries, suspicious = mapped_shapes(mapped_raw)
        view: dict[str, Any] = {
            "available": True,
            "mapped_with": f"{type(model).__name__}({getattr(model, 'model_name', '')})",
            "total": len(entries),
            "omitted": max(0, len(entries) - KEEP_MESSAGES),
            "messages": entries[-KEEP_MESSAGES:],
            "suspicious": suspicious,
        }
        if suspicious:
            # The expensive part (one mapping per message) only runs when it matters.
            sources = await _sources(model, messages, params, settings, entries)
            if sources is not None:
                view["suspicious_source"] = [
                    {"provider": i, "message": sources[i]} for i in suspicious
                ]  # message None: an instruction (system) message
        return view
    except Exception as error:
        # The mapping is a private internal; a change there must never break a run.
        return {"available": False, "reason": f"{type(error).__name__}"}


async def request_shape(request_context: ModelRequestContext, number: int) -> dict[str, Any]:
    """Shape record of the request about to be sent (``number`` counts from 1)."""
    shapes = message_shapes(request_context.messages)
    return {
        "shape_version": SHAPE_VERSION,
        "pydantic_ai": pydantic_ai.__version__,
        "request_number": number,
        "messages_total": len(shapes),
        "messages_omitted": max(0, len(shapes) - KEEP_MESSAGES),
        "messages": shapes[-KEEP_MESSAGES:],
        "provider": await _provider_view(request_context),
    }


def error_info(error: BaseException) -> dict[str, Any]:
    """Class and HTTP status of an exception from the model call; never its text or body."""

    def status(exc: BaseException, depth: int = 0) -> int | None:
        code = getattr(exc, "status_code", None)
        if isinstance(code, int):
            return code
        if depth < 3:
            for inner in getattr(exc, "exceptions", ()) or ():
                if isinstance(inner, BaseException) and (found := status(inner, depth + 1)):
                    return found
        return None

    return {"error_class": type(error).__name__, "status_code": status(error)}


def failed_request(
    shape: dict[str, Any] | None, error: dict[str, Any] | None
) -> dict[str, Any] | None:
    """The record stored with a failed run, or ``None`` if no request was observed.

    ``model_call_failed`` is false when the run failed elsewhere (usage limit, tool error); the
    shape is then the one of the last request that was sent, not of a rejected one.
    """
    if shape is None:
        return None
    return {
        **shape,
        "model_call_failed": error is not None
        and error.get("request_number") == shape["request_number"],
        "error_class": (error or {}).get("error_class"),
        "status_code": (error or {}).get("status_code"),
    }


__all__ = [
    "KEEP_MESSAGES",
    "SHAPE_VERSION",
    "error_info",
    "failed_request",
    "mapped_shapes",
    "message_shapes",
    "request_shape",
    "short_id",
]
