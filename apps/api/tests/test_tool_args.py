"""Repair of hand-written tool arguments (docs/problems: Tonie cloud shelf, no progress at all)."""

import json
from pathlib import Path
from typing import Any

import pytest
from design_fixtures import fixture_design
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from homeworking.bootstrap import build_container
from homeworking.modules.agent.args import parse_json, quote_bare_expressions
from homeworking.modules.agent.tools import AgentDeps, build_agent
from homeworking.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures" / "tool_args"


def test_bare_expressions_are_quoted() -> None:
    text = '{"at": [150, 0, 18 + (i + 1) * (height_mm - 36) / (shelves + 1)], "n": shelves}'
    assert json.loads(quote_bare_expressions(text)) == {
        "at": [150, 0, "18 + (i + 1) * (height_mm - 36) / (shelves + 1)"],
        "n": "shelves",
    }


def test_literals_strings_and_nested_quotes_stay_untouched() -> None:
    text = '{"a": -1.5e2, "b": true, "c": null, "d": "x + 1, y]", "e": if(wood == "oak", 2, 3)}'
    assert json.loads(quote_bare_expressions(text)) == {
        "a": -150.0,
        "b": True,
        "c": None,
        "d": "x + 1, y]",
        "e": 'if(wood == "oak", 2, 3)',
    }


def test_design_from_the_bug_report_is_parsed() -> None:
    """The model's real save_design argument: unquoted formulas made every retry fail."""
    design = parse_json((FIXTURES / "tonie_cloud_shelf_bare_expressions.txt").read_text())
    shelf = next(p for p in design["parts"] if p["id"] == "shelf")
    assert shelf["at"] == [150, 0, "18 + (i + 1) * (height_mm - 36) / (shelves + 1)"]


def test_brace_instead_of_bracket_closes_the_list() -> None:
    """Kids' podium run: the parts list ended with ``}}`` instead of ``}]`` before "steps"."""
    design = parse_json((FIXTURES / "podest_kinder_wrong_closer.txt").read_text())
    assert design["parts"][-1]["item"] == "foot_rubber_40"
    assert design["steps"][0]["title"] == "Eckenpfosten aufstellen"
    assert design["finish"] == "finish_hardwax_750"


def test_surplus_brace_inside_a_list_is_still_dropped() -> None:
    assert parse_json('{"parts": [{"id": "a"}}, {"id": "b"}]}') == {
        "parts": [{"id": "a"}, {"id": "b"}]
    }


def test_unrepairable_json_names_position_and_cause() -> None:
    with pytest.raises(ValueError, match=r"bei Zeichen 8.*Anführungszeichen"):
        parse_json('{"a": 1 "b": 2}')


def _design_with_bare_expression() -> str:
    """The shutter design as hand-written JSON with one formula not in quotes."""
    text = json.dumps(fixture_design("window_shutter").model_dump(mode="json"))
    expr = next(
        v
        for part in fixture_design("window_shutter").parts
        for v in (*(part.size or ()), *(part.at or ()))
        if isinstance(v, str) and " " in v
    )
    assert json.dumps(expr) in text
    return text.replace(json.dumps(expr), expr, 1)


@pytest.mark.parametrize("as_raw_call", [False, True], ids=["design-string", "raw-tool-call"])
async def test_save_design_accepts_unquoted_formulas(settings: Settings, as_raw_call: bool) -> None:
    """Both shapes seen in production succeed on the first call, without a retry."""
    design = _design_with_bare_expression()
    args: str | dict[str, Any] = (
        # OpenAI-style providers deliver the whole call as one (here: invalid) JSON string.
        '{"title": "Fensterladen", "design": ' + design + "}"
        if as_raw_call
        else {"title": "Fensterladen", "design": design}
    )
    results: list[str] = []

    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        last = messages[-1]
        kinds = {"tool-return", "retry-prompt"}
        returns = [p for p in last.parts if getattr(p, "part_kind", "") in kinds]
        if isinstance(last, ModelRequest) and returns:
            results.extend(p.part_kind for p in returns)
            return ModelResponse(parts=[TextPart("Fertig.")])
        return ModelResponse(parts=[ToolCallPart("save_design", args)])

    container = build_container(settings)
    await container.create_schema()
    try:
        owner = (await container.identity.create_guest()).id
        agent = build_agent(FunctionModel(respond))
        deps = AgentDeps(owner_id=owner, projects=container.projects, project_id=None, trace_id="t")
        await agent.run("Ein Fensterladen", deps=deps)
        assert results == ["tool-return"]
        assert deps.project_id is not None
    finally:
        await container.close()


async def test_cloud_design_covers_the_tonie_brief(settings: Settings) -> None:
    """Tonie shelf, wall-mounted, untreated: the design the model writes for the brief builds."""
    design = fixture_design("cloud_shelf").model_dump(mode="json", exclude_defaults=True)
    design.update(support="wall")
    design.pop("finish", None)

    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "save_design",
                        {
                            "design": design,
                            "title": "Tonieregal Wolke",
                            "params": {"shelves": 3, "material": "glulam_spruce_18"},
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
        await agent.run("Tonieregal mit Wolke, Fichte, an der Wand", deps=deps)
        assert deps.project_id is not None
        model = await container.projects.get(owner, deps.project_id)
        saved = model.inputs.design
        assert (saved.support, saved.finish) == ("wall", None)
        names = " ".join(line.name for line in model.result.bom)
        # Base and shelves in spruce; the cloud stays birch plywood (spruce panels are 600 mm).
        assert "Leimholzplatte Fichte" in names
    finally:
        await container.close()
