"""Deterministic offline stand-ins for the stage models (``LLM_MODE=test``).

They read the same prompt a real model gets and answer with the same output tool, so tests, E2E
runs and local development need no API key. They are deliberately simple: intake reads a few
German phrasings, the skeleton is one box module and a module is a plywood carcass. They are never
shown to a real model.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

_NUM = r"(\d+(?:[.,]\d+)?)"
_UNIT = r"(mm|cm|m)\b"
_DIMS = re.compile(
    rf"{_NUM}\s*(?:{_UNIT})?\s*[x×*]\s*{_NUM}\s*(?:{_UNIT})?"
    rf"(?:\s*[x×*]\s*{_NUM}\s*(?:{_UNIT})?)?",
    re.IGNORECASE,
)
_UNITS = {"mm": 1.0, "cm": 10.0, "m": 1000.0}
_WOODS = {"lärche": "larch", "douglasie": "douglas", "fichte": "spruce", "eiche": "oak"}
_DEFAULT_SIZE = (800, 400, 800)


def _mm(value: str, unit: str | None, fallback: str | None) -> int:
    factor = _UNITS[(unit or fallback or "cm").lower()]
    return round(float(value.replace(",", ".")) * factor)


def read_text(description: str) -> dict[str, Any]:
    """The facts a phrase such as '60 x 30 x 180 cm, draußen, an der Wand' states."""
    text = description.lower()
    updates: dict[str, Any] = {}
    if match := _DIMS.search(description):
        a, ua, b, ub, c, uc = match.groups()
        unit = ua or ub or uc
        names = ("width_mm", "depth_mm", "height_mm")
        for name, (value, own) in zip(names, ((a, ua), (b, ub), (c, uc)), strict=True):
            if value is not None:
                updates[name] = _mm(value, own, unit)
    if re.search(r"drau(?:ß|ss)en|au(?:ß|ss)en|garten|balkon|terrasse", text):
        updates["use"] = "outdoor"
    elif re.search(r"\binnen\b|drinnen|wohnzimmer|kinderzimmer|zimmer", text):
        updates["use"] = "indoor"
    if "an der wand" in text or "wandmontage" in text:
        updates["support"] = "wall"
    elif "freistehend" in text:
        updates["support"] = "floor"
    if "höchstens" in text or "maximal" in text or "bis zu" in text:
        updates["size_mode"] = "max"
    for word, key in _WOODS.items():
        if word in text:
            updates["wood"] = key
    return updates


def _user_text(messages: list[ModelMessage], *, first: bool = False) -> str:
    """The latest user prompt (or the first one: repair rounds append a prompt to the history)."""
    for message in messages if first else reversed(messages):
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    return part.content
    return ""


def _spec_line(text: str) -> dict[str, Any]:
    for line in text.splitlines():
        if line.startswith("Steckbrief: "):
            loaded: dict[str, Any] = json.loads(line.removeprefix("Steckbrief: "))
            return loaded
    return {}


def _answer(info: AgentInfo, data: dict[str, Any]) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, data)])


def intake_model() -> FunctionModel:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        spec = _spec_line(_user_text(messages))
        return _answer(info, {"updates": read_text(str(spec.get("description", "")))})

    return FunctionModel(respond, model_name="offline-intake")


def _length(name: str, label: str, value: int) -> dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "kind": "length",
        "default": value,
        "min": max(1, value // 2),
        "max": value * 2,
    }


def skeleton_model() -> FunctionModel:
    """One box module with the customer's dimensions (or a small default)."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        spec = _spec_line(_user_text(messages))
        width, depth, height = (
            int(spec.get(key, default))
            for key, default in zip(
                ("width_mm", "depth_mm", "height_mm"), _DEFAULT_SIZE, strict=True
            )
        )
        return _answer(
            info,
            {
                "object_type": "Objekt",
                "summary": "Objekt nach Kundenangabe",
                "params": [
                    _length("width_mm", "Breite (mm)", width),
                    _length("depth_mm", "Tiefe (mm)", depth),
                    _length("height_mm", "Höhe (mm)", height),
                ],
                "modules": [
                    {
                        "id": "body",
                        "title": "Korpus",
                        "role": "Gesamtes Objekt",
                        "origin": [0, 0, 0],
                        "size": ["width_mm", "depth_mm", "height_mm"],
                    }
                ],
            },
        )

    return FunctionModel(respond, model_name="offline-skeleton")


def _line(text: str, label: str) -> str | None:
    for line in text.splitlines():
        if line.startswith(label):
            return line.removeprefix(label)
    return None


def _panel(
    part_id: str, name: str, size: list[Any], at: list[Any], material: str = "plywood_birch_18"
) -> dict[str, Any]:
    return {"id": part_id, "name": name, "material": material, "size": size, "at": at}


def module_model() -> FunctionModel:
    """A carcass of four plywood panels filling the module box: sides, bottom and top."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        text = _user_text(messages, first=True)
        brief: dict[str, Any] = json.loads(_line(text, "Modul: ") or "{}")
        width, depth, height = (f"({v})" if isinstance(v, str) else str(v) for v in brief["size"])
        thickness = 18
        inner = f"{width} - {2 * thickness}"
        parts = [
            _panel("left", "Seitenteil links", [thickness, depth, height], [0, 0, 0]),
            _panel(
                "right", "Seitenteil rechts", [thickness, depth, height], [f"{width} - 18", 0, 0]
            ),
            _panel("bottom", "Boden", [inner, depth, thickness], [thickness, 0, 0]),
            _panel("top", "Deckel", [inner, depth, thickness], [thickness, 0, f"{height} - 18"]),
        ]
        return _answer(info, {"module": brief["id"], "parts": parts})

    return FunctionModel(respond, model_name="offline-modules")


_EXPLANATION = (
    "Der Korpus besteht aus Platten, weil sie formstabil und einfach zuzuschneiden sind.\n\n"
    "Die Seitenteile stehen auf dem Boden und tragen Boden und Deckel; verschraubt wird von "
    "außen durch die Seitenteile.\n\n"
    "Die Annahmen stammen aus deinem Steckbrief; Maße und Material lassen sich leicht ändern."
)


def docs_model() -> FunctionModel:
    """Generic explanation and one step per module, read from the ``- id (title): ...`` lines."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        text = _user_text(messages, first=True)
        steps = [
            {
                "module": m.group(1),
                "title": m.group(2),
                "text": f"Montiere {m.group(2)}: bündig ausrichten, Diagonalen prüfen, verschrauben.",
            }
            for m in re.finditer(r"^- ([a-z][a-z0-9]*) \((.+?)\):", text, re.MULTILINE)
        ]
        return _answer(info, {"explanation": _EXPLANATION, "steps": steps})

    return FunctionModel(respond, model_name="offline-docs")
