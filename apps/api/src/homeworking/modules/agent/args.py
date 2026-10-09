"""Repair of hand-written JSON in tool arguments.

Models write whole designs as JSON by hand. Two mistakes are common and cost every retry,
because the model reads the error as "pass an object, not a string" and repeats the call:

- arithmetic written as a bare value, e.g. ``"at": [0, 0, 18 + i * 116]`` instead of
  ``"18 + i * 116"`` (the design schema takes such expressions as strings anyway),
- one closing brace too many or too few at the end of a long design.

Both are repaired in one place, for the raw arguments of every tool call (``RepairToolArgs``)
and for object arguments that arrive as a JSON-encoded string (``JsonTolerant``). Anything else
is reported with its position and the likely cause. Repaired values are still validated by
pydantic and checked by the engine; nothing is evaluated here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BeforeValidator
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import ToolDefinition

_CLOSERS = {"}": "{", "]": "["}
_OPENERS = {v: k for k, v in _CLOSERS.items()}

HINT = (
    "Rechenausdrücke stehen als String in Anführungszeichen, z. B. "
    '"at": [0, 0, "18 + (i + 1) * 116"]; Objekte als JSON-Objekt, nicht als String.'
)


def _string_end(text: str, start: int) -> int:
    """Index after the JSON string that opens at ``start`` (or the end of the text)."""
    i = start + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == '"':
            return i + 1
        i += 1
    return len(text)


def _value_end(text: str, start: int) -> int | None:
    """End of a bare value: the next , ] or } outside parentheses and strings.

    None if the text there is no expression: a string or a colon outside parentheses means
    the JSON is broken in another way (e.g. a missing comma), which must not be hidden.
    """
    depth = 0
    i = start
    while i < len(text):
        char = text[i]
        if char in '":':
            if depth == 0:
                return None
            if char == '"':
                i = _string_end(text, i)
                continue
        elif char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char in ",]}" and depth == 0:
            return i
        i += 1
    return i


def _is_json_literal(token: str) -> bool:
    try:
        value = json.loads(token)
    except json.JSONDecodeError:
        return False
    return not isinstance(value, (dict, list))


def quote_bare_expressions(text: str) -> str:
    """Put bare values that are no JSON literal (``18 + i * 116``, ``width_mm``) in quotes."""
    out: list[str] = []
    expect_value = False
    i = 0
    while i < len(text):
        char = text[i]
        if char == '"':
            end = _string_end(text, i)
            out.append(text[i:end])
            i, expect_value = end, False
        elif char in ":[,":
            out.append(char)
            i, expect_value = i + 1, True
        elif char.isspace():
            out.append(char)
            i += 1
        elif expect_value and char not in "{}]" and (stop := _value_end(text, i)) is not None:
            token = text[i:stop].rstrip()
            out.append(token if _is_json_literal(token) else json.dumps(token, ensure_ascii=False))
            out.append(text[i + len(token) : stop])
            i, expect_value = stop, False
        else:
            out.append(char)
            i, expect_value = i + 1, False
    return "".join(out)


def balance_brackets(text: str) -> str:
    """Drop closing brackets without a matching opener and close brackets left open."""
    out: list[str] = []
    stack: list[str] = []
    in_string = escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in _OPENERS:
            stack.append(char)
        elif char in _CLOSERS:
            if not stack or stack[-1] != _CLOSERS[char]:
                continue
            stack.pop()
        out.append(char)
    out.extend(_OPENERS[opener] for opener in reversed(stack))
    return "".join(out)


def parse_json(text: str) -> Any:
    """Parse hand-written JSON, repairing bare expressions and unbalanced brackets.

    Raises ValueError with the position, the surrounding text and the likely cause.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        error = exc
    for repair in (balance_brackets, quote_bare_expressions):
        text = repair(text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    original = error.doc
    context = original[max(0, error.pos - 40) : error.pos + 20]
    raise ValueError(
        f"Kein gültiges JSON ({error.msg} bei Zeichen {error.pos}: …{context}…). {HINT}"
    )


def _parse_json_string(value: Any) -> Any:
    """Accept an object argument that the model sent as a JSON-encoded string."""
    return parse_json(value) if isinstance(value, str) else value


# Object-typed tool arguments: a JSON string is decoded (and repaired) before validation.
JsonTolerant = BeforeValidator(_parse_json_string)


@dataclass
class RepairToolArgs(AbstractCapability[Any]):
    """Repair the raw JSON of a tool call before pydantic-ai validates it.

    OpenAI-style providers deliver tool arguments as a string; a single bare expression in a
    design makes the whole call invalid JSON and pydantic only reports "Invalid JSON".
    """

    async def before_tool_validate(
        self,
        ctx: RunContext[Any],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: str | dict[str, Any],
    ) -> str | dict[str, Any]:
        if not isinstance(args, str) or not args.strip():
            return args
        try:
            parsed = parse_json(args)
        except ValueError as exc:
            raise ModelRetry(str(exc)) from None
        return parsed if isinstance(parsed, dict) else args

    @classmethod
    def get_serialization_name(cls) -> str | None:
        return None
