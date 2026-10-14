import asyncio
import json
from typing import Any, cast
from uuid import uuid4

import pytest
from api_designs import design as offline_design
from design_fixtures import fixture_design
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from calc_engine.catalog import default_catalog
from homeworking.bootstrap import build_container
from homeworking.modules.agent.args import _parse_json_string
from homeworking.modules.agent.tools import (
    AgentDeps,
    build_agent,
    design_materials,
)
from homeworking.settings import Settings


def test_materials_offer_lumber_in_any_species() -> None:
    materials = design_materials(default_catalog())
    species = {s["species"]: s for s in materials["lumber"]["species"]}
    assert {"douglas", "larch", "oak", "spruce"} <= species.keys()
    assert species["douglas"]["outdoor"] is True
    hardware = {i["id"]: i.get("hardware_type") for i in materials["catalog_items"]}
    assert hardware["hinge_strap_200"] == "hinge"
    assert hardware["latch_barrel_80"] == "latch"


async def test_parallel_tool_calls_do_not_conflict(settings: Settings) -> None:
    """The model may change the project and store an explanation in one response."""

    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        last = messages[-1]
        if isinstance(last, ModelRequest) and any(
            getattr(p, "part_kind", "") == "tool-return" for p in last.parts
        ):
            return ModelResponse(parts=[TextPart("Fertig.")])
        return ModelResponse(
            parts=[
                ToolCallPart(
                    "change_project",
                    {"command": {"type": "set_parameters", "values": {"width_mm": 1500}}},
                ),
                ToolCallPart("add_explanation", {"text": "Breiter für mehr Pflanzfläche."}),
            ]
        )

    container = build_container(settings)
    await container.create_schema()
    try:
        owner = (await container.identity.create_guest()).id
        created = await container.projects.create(
            owner, title="A", design=offline_design("raised_bed"), params={}
        )
        agent = build_agent(FunctionModel(respond))
        deps = AgentDeps(
            owner_id=owner, projects=container.projects, project_id=created.project.id, trace_id="t"
        )
        await agent.run("Breiter und erklär es", deps=deps)
        model = await container.projects.get(owner, created.project.id)
        assert model.inputs.params["width_mm"] == 1500
        assert [n.text for n in model.inputs.notes] == ["Breiter für mehr Pflanzfläche."]
    finally:
        await container.close()


async def test_create_stores_explanation_without_extra_round_trip(settings: Settings) -> None:
    """The explanation travels with the creating call, so no second model request is needed."""
    requests = 0

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal requests
        requests += 1
        if requests == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "save_design",
                        {
                            "design": offline_design("shelf").model_dump(mode="json"),
                            "title": "Regal",
                            "explanation": "Leimholz, stumpf verschraubt.",
                        },
                    )
                ]
            )
        return ModelResponse(parts=[TextPart("Fertig.")])

    container = build_container(settings)
    await container.create_schema()
    try:
        owner = (await container.identity.create_guest()).id
        agent = build_agent(FunctionModel(respond))
        deps = AgentDeps(owner_id=owner, projects=container.projects, project_id=None, trace_id="t")
        await agent.run("Ein Regal", deps=deps)
        assert requests == 2
        assert deps.project_id is not None
        model = await container.projects.get(owner, deps.project_id)
        assert [n.text for n in model.inputs.notes] == ["Leimholz, stumpf verschraubt."]
    finally:
        await container.close()


async def test_design_sent_as_json_string_is_accepted(settings: Settings) -> None:
    """Models often serialise the large design argument into a string; it must still validate."""
    design = fixture_design("window_shutter").model_dump_json()
    results: list[str] = []

    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        last = messages[-1]
        kinds = {"tool-return", "retry-prompt"}
        returns = [p for p in last.parts if getattr(p, "part_kind", "") in kinds]
        if isinstance(last, ModelRequest) and returns:
            results.extend(p.part_kind for p in returns)
            return ModelResponse(parts=[TextPart("Fertig.")])
        return ModelResponse(
            parts=[
                ToolCallPart(
                    "save_design",
                    {"title": "Fensterladen", "design": design, "params": '{"width_mm": 600}'},
                )
            ]
        )

    container = build_container(settings)
    await container.create_schema()
    try:
        owner = (await container.identity.create_guest()).id
        agent = build_agent(FunctionModel(respond))
        deps = AgentDeps(owner_id=owner, projects=container.projects, project_id=None, trace_id="t")
        await agent.run("Ein Fensterladen", deps=deps)
        assert results == ["tool-return"]
        assert deps.project_id is not None
        model = await container.projects.get(owner, deps.project_id)
        assert model.inputs.params["width_mm"] == 600
    finally:
        await container.close()


def test_json_string_with_unbalanced_brackets_is_repaired() -> None:
    """A stray or missing brace at the end of a design string must not cost a retry."""
    design = fixture_design("window_shutter").model_dump(mode="json")
    text = json.dumps(design)
    # One brace too many inside the last list (the bug report's case) and one missing at the end.
    stray = text[: text.rindex("]")] + "}" + text[text.rindex("]") :]
    assert _parse_json_string(stray) == design
    assert _parse_json_string(text[:-1]) == design
    # Brackets inside strings are left alone.
    assert _parse_json_string('{"summary": "a {b] c"}}') == {"summary": "a {b] c"}


def test_invalid_json_string_names_the_error_position() -> None:
    """The model must see where its JSON is broken, not only 'Input should be an object'."""
    with pytest.raises(ValueError, match=r"bei Zeichen 8: …\{\"a\": 1 \"b\": 2\}…"):
        _parse_json_string('{"a": 1 "b": 2}')


def test_the_model_sees_no_packs_or_templates() -> None:
    """Every project is a one-off design (ADR-0008): no catalogue of ready-made constructions."""
    seen: list[AgentInfo] = []

    def capture(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(info)
        return ModelResponse(parts=[TextPart("ok")])

    deps = AgentDeps(owner_id=uuid4(), projects=cast(Any, None), project_id=None, trace_id="t")
    asyncio.run(build_agent(FunctionModel(capture)).run("x", deps=deps))
    names = {t.name for t in seen[0].function_tools}
    assert names.isdisjoint(
        {"create_project", "create_from_template", "get_template_design", "list_construction_packs"}
    )
    assert "save_design" in names
    instructions = seen[0].instructions or ""
    assert "create_from_template" not in instructions
    assert "Planbar ohne freien Entwurf" not in instructions
