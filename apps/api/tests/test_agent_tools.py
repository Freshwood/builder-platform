import json

import pytest
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from calc_engine.assembly.templates import template
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
        created = await container.projects.create(owner, pack_id="raised_bed", title="A", params={})
        agent = build_agent(FunctionModel(respond), container.engine)
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
            assert "Vorlage shelf" in (info.instructions or "")
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "create_from_template",
                        {
                            "template_key": "shelf",
                            "title": "Regal",
                            "params": {},
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
        agent = build_agent(FunctionModel(respond), container.engine)
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
    design = template("window_shutter").design.model_dump_json()
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
        agent = build_agent(FunctionModel(respond), container.engine)
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
    design = template("window_shutter").design.model_dump(mode="json")
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


async def test_template_can_be_built_untreated_in_pine(settings: Settings) -> None:
    """'Kiefer, unbehandelt' fits the shutter template: no free design, no finish in the list."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            assert "wood=douglas|larch|oak|pine|spruce" in (info.instructions or "")
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "create_from_template",
                        {
                            "template_key": "window_shutter",
                            "title": "Fensterladen",
                            # The flag and use often end up among the params
                            "params": {
                                "width_mm": 310,
                                "height_mm": 380,
                                "wood": "pine",
                                "untreated": True,
                                "use": "outdoor",
                            },
                        },
                    )
                ]
            )
        return ModelResponse(parts=[TextPart("Fertig.")])

    container = build_container(settings)
    await container.create_schema()
    try:
        owner = (await container.identity.create_guest()).id
        agent = build_agent(FunctionModel(respond), container.engine)
        deps = AgentDeps(owner_id=owner, projects=container.projects, project_id=None, trace_id="t")
        await agent.run("Fensterläden aus Kiefer, unbehandelt", deps=deps)
        assert deps.project_id is not None
        model = await container.projects.get(owner, deps.project_id)
        names = [line.name for line in model.result.bom]
        assert any("Kiefer" in name for name in names)
        assert not any("öl" in name.lower() or "lasur" in name.lower() for name in names)
    finally:
        await container.close()
