"""Deterministic offline planner used as the model in ``LLM_MODE=test``.

It understands a small set of German phrasings via patterns and calls the same tools as a real
LLM. This keeps CI, E2E tests and local development free of API keys and network access.

Like a real model it drafts the design itself and saves it with ``save_design``. It can only
draft the few constructions in ``offline_designs/``; they stand in for what the LLM would write
and are never shown to a real model (ADR-0008). Boxy furniture (``_PLANNED``) goes to
``plan_design``, i.e. through the staged pipeline with its offline stage models (ADR-0010).
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path
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

from construction_model.assembly import AssemblyDesign

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
# Furniture the offline pipeline stand-ins can plan (a plywood carcass), see ``_plan_call``.
_PLANNED = ("schrank", "kommode", "podest", "truhe", "kiste")
_OTHER_PROJECTS = ("terrasse", "carport", "gartenhaus", "schuppen", "zaun", "pergola", "schrank")
_DIMS3 = re.compile(
    rf"{_NUM}\s*(?:{_UNIT})?\s*[x×*]\s*{_NUM}\s*(?:{_UNIT})?\s*[x×*]\s*{_NUM}\s*(?:{_UNIT})?",
    re.IGNORECASE,
)
_COUNT = re.compile(
    r"(\d+)\s*(?:fach)?(?:böden|boeden|fächer|faecher|sitzlatten|latten|flügel|fluegel)",
    re.IGNORECASE,
)
_LENGTH = re.compile(rf"{_NUM}\s*{_UNIT}\s*(?:lang|breit)", re.IGNORECASE)
_WIDTH = re.compile(rf"breite\s*(?:von\s*)?(?:ca\.?\s*)?{_NUM}\s*{_UNIT}", re.IGNORECASE)
# Order in which dimensions of "a × b × c" map to design parameters.
_DIM_ORDER = ("width_mm", "length_mm", "depth_mm", "height_mm")
_DESIGNS = Path(__file__).resolve().parent / "offline_designs"


@dataclass(frozen=True)
class OfflineDesign:
    """A construction the offline planner can draft: trigger words, title and design."""

    key: str
    title: str
    keywords: tuple[str, ...]
    design: AssemblyDesign


@cache
def offline_designs() -> tuple[OfflineDesign, ...]:
    def load(key: str) -> AssemblyDesign:
        path = _DESIGNS / f"{key}.json"
        return AssemblyDesign.model_validate(json.loads(path.read_text(encoding="utf-8")))

    return (
        OfflineDesign("raised_bed", "Hochbeet", ("hochbeet",), load("raised_bed")),
        OfflineDesign("shelf", "Regal", ("regal", "bücherregal", "buecherregal"), load("shelf")),
    )


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
    return params


def _match_design(text: str) -> OfflineDesign | None:
    best: tuple[int, OfflineDesign] | None = None
    for candidate in offline_designs():
        for keyword in candidate.keywords:
            if re.search(rf"\b{re.escape(keyword)}", text) and (
                best is None or len(keyword) > best[0]
            ):
                best = (len(keyword), candidate)
    return best[1] if best else None


def _design_params(design: AssemblyDesign, text: str) -> dict[str, Any]:
    """Map simple phrasings to design parameters (names that the design actually has)."""
    names = [p.name for p in design.params]
    dims = [n for n in _DIM_ORDER if n in names]
    params: dict[str, Any] = {}
    if m := _DIMS3.search(text):
        unit = m.group(6) or m.group(4) or m.group(2)
        values = [
            _to_mm(m.group(1), m.group(2) or unit),
            _to_mm(m.group(3), m.group(4) or unit),
            _to_mm(m.group(5), unit),
        ]
        params |= dict(zip(dims, values, strict=False))
    elif m := _DIMS.search(text):
        unit = m.group(4) or m.group(2)
        values = [_to_mm(m.group(1), m.group(2) or unit), _to_mm(m.group(3), unit)]
        params |= dict(zip(dims, values, strict=False))
    elif (m := _LENGTH.search(text)) and dims:
        params[dims[0]] = _to_mm(m.group(1), m.group(2))
    elif (m := _WIDTH.search(text)) and "width_mm" in names:
        params["width_mm"] = _to_mm(m.group(1), m.group(2))
    if (m := _HEIGHT.search(text)) and "height_mm" in names:
        value, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        params["height_mm"] = _to_mm(value, unit)
    if m := _COUNT.search(text):
        counts = [p.name for p in design.params if p.kind == "count"]
        if counts:
            params[counts[0]] = int(m.group(1))
    bools = {p.name for p in design.params if p.kind == "bool"}
    for name, words in {
        "backrest": ("lehne",),
        "castors": ("rollen",),
        "back_panel": ("rückwand", "rueckwand"),
        "lower_shelf": ("ablage",),
    }.items():
        if name not in bools:
            continue
        for word in words:
            if re.search(rf"ohne\s+(\w+\s+)?{word}", text):
                params[name] = False
            elif re.search(rf"mit\s+(\w+\s+)?{word}", text):
                params[name] = True
    choices = {o.value: p.name for p in design.params if p.kind == "choice" for o in p.options}
    for value, wood in _feature_params(text).items():
        if value == "wood" and wood in choices:
            params[choices[wood]] = wood
    if "multiplex" in text and "plywood_birch_18" in choices:
        params[choices["plywood_birch_18"]] = "plywood_birch_18"
    return params


def _plan_call(raw: str, text: str) -> ToolCall | None:
    """Boxy furniture with dimensions goes through the staged pipeline (ADR-0010): the stand-in
    only fills the brief, like a real model would."""
    word = next((w for w in _PLANNED if w in text), None)
    if word is None:
        return None
    if m := _DIMS3.search(text):
        unit = m.group(6) or m.group(4) or m.group(2)
        width, depth, height = (
            _to_mm(m.group(1), m.group(2) or unit),
            _to_mm(m.group(3), m.group(4) or unit),
            _to_mm(m.group(5), unit),
        )
    elif m := _DIMS.search(text):
        unit = m.group(4) or m.group(2)
        width, depth, height = (
            _to_mm(m.group(1), m.group(2) or unit),
            _to_mm(m.group(3), unit),
            800,
        )
    else:
        return None
    spec: dict[str, Any] = {
        "description": raw[:2000],
        "width_mm": width,
        "depth_mm": depth,
        "height_mm": height,
    }
    if re.search(r"drau(?:ß|ss)en|außen|garten|terrasse", text):
        spec["use"] = "outdoor"
    elif re.search(r"drinnen|\binnen\b|zimmer", text):
        spec["use"] = "indoor"
    if "an der wand" in text:
        spec["support"] = "wall"
    for word, key in _WOODS.items():
        if word in text:
            spec["wood"] = key
    return ToolCall("plan_design", {"spec": spec, "title": word.capitalize()})


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

    if "hochbeet" in text and not _DIMS.search(text):
        return (
            "Gern plane ich dein Hochbeet! Wie lang und wie breit soll es werden "
            "(z. B. 2 × 1 m), und welche Höhe wünschst du dir?"
        )

    if drafted := _match_design(text):
        params = _design_params(drafted.design, text)
        if drafted.key == "raised_bed" and "width_mm" in params and "length_mm" in params:
            # "2 × 1 m": the longer side is the length.
            a, b = params["width_mm"], params["length_mm"]
            params["length_mm"], params["width_mm"] = max(a, b), min(a, b)
        return [
            ToolCall(
                "save_design",
                {
                    "design": drafted.design.model_dump(mode="json", exclude_defaults=True),
                    "title": drafted.title,
                    "params": params,
                },
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

    if (planned := _plan_call(raw, text)) is not None:
        return [planned]

    if any(word in text for word in _OTHER_PROJECTS):
        return (
            "Das klingt nach einem spannenden Vorhaben! Im Offline-Modus kann ich nur ein Hochbeet "
            "oder ein Regal entwerfen. Mit angebundenem Sprachmodell entwerfe ich jedes Projekt "
            "aus Holz und Platten individuell nach deinen Angaben. Tragende Bauwerke wie Carport "
            "oder Gartenhaus brauchen eine Fachplanung."
        )
    return (
        "Ich helfe dir, dein Bauvorhaben zu planen. Beschreibe mir, was du bauen möchtest – "
        "zum Beispiel: „Hochbeet 2 × 1 m, 80 cm hoch, aus Lärche“ oder „Regal 80 × 30 × 180 cm "
        "mit 5 Böden“."
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
    verb = {
        "created": "erstellt",
        "replanned": "neu geplant",
        "changed": "aktualisiert",
        "undone": "zurückgesetzt",
    }.get(content.get("action", ""), "geladen")
    figures = project.get("key_figures", {})
    lines = [f"Ich habe dein Projekt {verb}: {project['summary']}."]
    if "Innenmaß" in figures:
        lines.append(
            f"Innenmaß {figures['Innenmaß']}, Füllvolumen {figures.get('Füllvolumen', '–')}."
        )
    elif figures:
        lines.append(" · ".join(f"{k} {v}" for k, v in list(figures.items())[1:3]) + ".")
    lines.append(f"Materialkosten (Richtwert): {project['material_cost_eur']}.")
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
