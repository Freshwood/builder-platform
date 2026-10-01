"""Deterministic offline planner used as the model in ``LLM_MODE=test``.

It understands a small set of German phrasings via patterns and calls the same tools as a real
LLM. This keeps CI, E2E tests and local development free of API keys and network access.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, DeltaToolCalls, FunctionModel

_NUM = r"(\d+(?:[.,]\d+)?)"
_UNIT = r"(mm|cm|m)\b"
_DIMS = re.compile(rf"{_NUM}\s*(?:{_UNIT})?\s*[x×*]\s*{_NUM}\s*(?:{_UNIT})?", re.IGNORECASE)
_HEIGHT = re.compile(
    rf"(?:{_NUM}\s*{_UNIT}\s*hoch)|(?:h(?:ö|oe)he\s*(?:von\s*)?(?:ca\.?\s*)?{_NUM}\s*{_UNIT})",
    re.IGNORECASE,
)
_DELTA = re.compile(
    rf"{_NUM}\s*{_UNIT}\s*(breiter|schmaler|l(?:ä|ae)nger|k(?:ü|ue)rzer|h(?:ö|oe)her|niedriger)",
    re.IGNORECASE,
)
_DELTA_PARAM = {
    "breiter": ("width_mm", 1),
    "schmaler": ("width_mm", -1),
    "länger": ("length_mm", 1),
    "laenger": ("length_mm", 1),
    "kürzer": ("length_mm", -1),
    "kuerzer": ("length_mm", -1),
    "höher": ("height_mm", 1),
    "hoeher": ("height_mm", 1),
    "niedriger": ("height_mm", -1),
}
_WOODS = {"lärche": "larch", "laerche": "larch", "douglasie": "douglas", "fichte": "spruce"}
_VARIANTS = {
    "günstig": "budget",
    "guenstig": "budget",
    "langlebig": "durable",
    "komfort": "comfort",
}
_OTHER_PROJECTS = ("terrasse", "carport", "gartenhaus", "schuppen", "zaun", "regal", "werkbank")


def _to_mm(value: str, unit: str | None) -> int:
    number = float(value.replace(",", "."))
    if unit is None:
        unit = "m" if number <= 10 else "cm" if number <= 500 else "mm"
    factor = {"mm": 1, "cm": 10, "m": 1000}[unit.lower()]
    return round(number * factor)


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any]


Decision = str | list[ToolCall]


def _feature_params(text: str) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for word, wood in _WOODS.items():
        if word in text:
            params["wood"] = wood
    if re.search(r"ohne\s+(noppen)?folie|ohne\s+noppenbahn", text):
        params["liner"] = False
    if re.search(r"ohne\s+(wühlmaus|wuehlmaus)?gitter", text):
        params["vole_mesh"] = False
    if re.search(r"sitzkante|abdeckleiste", text):
        params["top_cap"] = True
    return params


def decide_for_user_text(raw: str) -> Decision:
    text = raw.lower()
    if re.search(r"rückgängig|rueckgaengig|undo", text):
        return [ToolCall("undo_last_change", {})]

    if delta := _DELTA.search(text):
        name, sign = _DELTA_PARAM[delta.group(3)]
        amount = _to_mm(delta.group(1), delta.group(2))
        return [
            ToolCall(
                "change_project",
                {"command": {"type": "change_parameter_by", "name": name, "delta": sign * amount}},
            )
        ]

    if "hochbeet" in text:
        params: dict[str, Any] = {}
        if dims := _DIMS.search(text):
            unit = dims.group(4) or dims.group(2)
            a = _to_mm(dims.group(1), dims.group(2) or unit)
            b = _to_mm(dims.group(3), unit)
            params["length_mm"], params["width_mm"] = max(a, b), min(a, b)
        if height := _HEIGHT.search(text):
            value, unit = (
                (height.group(1), height.group(2))
                if height.group(1)
                else (height.group(3), height.group(4))
            )
            params["height_mm"] = _to_mm(value, unit)
        params |= _feature_params(text)
        if "length_mm" not in params:
            return (
                "Gern plane ich dein Hochbeet! Wie lang und wie breit soll es werden "
                "(z. B. 2 × 1 m), und welche Höhe wünschst du dir?"
            )
        return [
            ToolCall(
                "create_project", {"pack_id": "raised_bed", "title": "Hochbeet", "params": params}
            )
        ]

    for word, key in _VARIANTS.items():
        if word in text and "variante" in text:
            return [
                ToolCall(
                    "change_project", {"command": {"type": "select_variant", "variant_key": key}}
                )
            ]

    if features := _feature_params(text):
        return [
            ToolCall("change_project", {"command": {"type": "set_parameters", "values": features}})
        ]

    if any(word in text for word in _OTHER_PROJECTS):
        return (
            "Das klingt nach einem spannenden Vorhaben! Aktuell kann ich Hochbeete vollständig "
            "planen – weitere Bauprojekte wie Terrasse, Carport oder Gartenhaus folgen bald. "
            "Möchtest du ein Hochbeet planen?"
        )
    return (
        "Ich helfe dir, dein Bauvorhaben zu planen. Beschreibe mir, was du bauen möchtest – "
        "zum Beispiel: „Hochbeet 2 × 1 m, 80 cm hoch, aus Lärche“."
    )


def _format_tool_result(content: Any) -> str:
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            return str(content)
    if not isinstance(content, dict):
        return "Erledigt."
    if "error" in content:
        return f"Das hat leider nicht geklappt: {content['error']}"
    if content.get("action") == "note_added":
        return "Ich habe die Erläuterung im Projekt gespeichert."
    project = content.get("project")
    if not project:
        return "Erledigt."
    verb = {"created": "erstellt", "changed": "aktualisiert", "undone": "zurückgesetzt"}.get(
        content.get("action", ""), "geladen"
    )
    figures = project.get("key_figures", {})
    lines = [
        f"Ich habe dein Projekt {verb}: {project['summary']}.",
        f"Innenmaß {figures.get('Innenmaß', '–')}, Füllvolumen {figures.get('Füllvolumen', '–')}.",
        f"Materialkosten (Richtwert): {project['material_cost_eur']}.",
    ]
    diff = content.get("diff")
    if diff and diff.get("material_cost_before_eur"):
        lines.append(f"Vorher lagen die Materialkosten bei {diff['material_cost_before_eur']}.")
    variants = ", ".join(
        f"{v['name']} ({v['material_cost_eur']})" for v in project.get("variants", [])
    )
    if variants and content.get("action") == "created":
        lines.append(f"Varianten zum Vergleich: {variants}.")
    lines.append("Zeichnungen, Material- und Zuschnittliste findest du rechts im Projekt.")
    return " ".join(lines)


def decide(messages: list[ModelMessage]) -> Decision:
    last = messages[-1]
    if not isinstance(last, ModelRequest):
        return "Wie kann ich helfen?"
    returns = [p for p in last.parts if isinstance(p, ToolReturnPart)]
    if returns:
        return " ".join(_format_tool_result(p.content) for p in returns)
    retries = [p for p in last.parts if isinstance(p, RetryPromptPart)]
    if retries:
        return "Das konnte ich nicht verarbeiten. Kannst du es anders formulieren?"
    prompts = [p for p in last.parts if isinstance(p, UserPromptPart)]
    text = " ".join(p.content if isinstance(p.content, str) else "" for p in prompts)
    return decide_for_user_text(text)


def _respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
    decision = decide(messages)
    if isinstance(decision, str):
        return ModelResponse(parts=[TextPart(decision)])
    return ModelResponse(parts=[ToolCallPart(c.name, c.args) for c in decision])


async def _stream(
    messages: list[ModelMessage], _info: AgentInfo
) -> AsyncIterator[str | DeltaToolCalls]:
    decision = decide(messages)
    if isinstance(decision, str):
        for word in re.findall(r"\S+\s*", decision):
            yield word
        return
    for index, call in enumerate(decision):
        yield {
            index: DeltaToolCall(
                name=call.name, json_args=json.dumps(call.args), tool_call_id=f"offline-{index}"
            )
        }


def offline_model() -> FunctionModel:
    return FunctionModel(_respond, stream_function=_stream, model_name="homeworking-offline")


def fixed_text_model(text: str) -> FunctionModel:
    """Model that always answers with a fixed text (used for safety referrals)."""

    def respond(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(text)])

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[str]:
        yield text

    return FunctionModel(respond, stream_function=stream, model_name="homeworking-safety")
