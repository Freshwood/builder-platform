"""Failed agent calls leave enough data in ``design_attempts`` to become a regression test."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from api_designs import design as offline_design
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from homeworking.bootstrap import build_container
from homeworking.modules.agent.tools import RAW_ARGS_MAX_CHARS, AgentDeps, build_agent
from homeworking.settings import Settings


@asynccontextmanager
async def run_calls(
    settings: Settings, calls: list[tuple[str, str | dict[str, Any]]]
) -> AsyncIterator[AgentDeps]:
    """Run an offline agent that sends ``calls`` one after another, then answers with text."""

    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        sent = sum(isinstance(m, ModelResponse) for m in messages)
        if sent < len(calls):
            name, args = calls[sent]
            return ModelResponse(parts=[ToolCallPart(name, args, tool_call_id=f"call_{sent}")])
        return ModelResponse(parts=[TextPart("Fertig.")])

    container = build_container(settings)
    await container.create_schema()
    try:
        owner = (await container.identity.create_guest()).id
        agent = build_agent(FunctionModel(respond))
        deps = AgentDeps(owner_id=owner, projects=container.projects, project_id=None, trace_id="t")
        await agent.run("Ein Regal", deps=deps)
        yield deps
    finally:
        await container.close()


def shelf() -> dict[str, Any]:
    design = offline_design("shelf").model_dump(mode="json", exclude_defaults=True)
    design["object_type"] = "Regal"
    return design


def below_floor() -> dict[str, Any]:
    """The shelf moved below the floor: the engine rejects it."""
    design = shelf()
    for part in design["parts"]:
        x, y, z = part["at"]
        part["at"] = [x, y, f"({z}) - 60"]
    return design


async def test_bare_expressions_are_recorded_verbatim_and_repaired(settings: Settings) -> None:
    text = json.dumps(shelf())
    expr = next(
        v
        for part in offline_design("shelf").parts
        for v in (*(part.size or ()), *(part.at or ()))
        if isinstance(v, str) and " " in v
    )
    assert json.dumps(expr) in text
    raw = '{"title": "Regal", "design": ' + text.replace(json.dumps(expr), expr, 1) + "}"
    async with run_calls(settings, [("save_design", raw)]) as deps:
        [entry] = deps.design_attempts
        assert deps.project_id is not None
    # The model's text is stored as sent (still invalid JSON), the repaired design is accepted.
    assert entry["raw_args"] == raw
    with pytest.raises(json.JSONDecodeError):
        json.loads(entry["raw_args"])
    assert (entry["tool"], entry["tool_call_id"]) == ("save_design", "call_0")
    assert (entry["outcome"], entry["accepted"], entry["errors"]) == ("accepted", True, [])
    assert entry["design"]["object_type"] == "Regal"
    json.dumps(deps.design_attempts)


async def test_extra_key_inside_design_is_recorded_as_invalid_args(settings: Settings) -> None:
    """The real bug: "explanation" inside design fails validation before the tool body runs."""
    args = {"title": "Regal", "design": {**shelf(), "explanation": "Warum so?"}}
    async with run_calls(
        settings, [("save_design", args), ("save_design", {"design": shelf()})]
    ) as deps:
        invalid, accepted = deps.design_attempts
    assert invalid["tool"] == "save_design"
    assert invalid["outcome"] == "invalid_args"
    assert invalid["accepted"] is False
    assert invalid["design"] is None
    assert invalid["raw_args"] == args
    assert any("design.explanation" in e and "extra_forbidden" in e for e in invalid["errors"])
    assert accepted["outcome"] == "accepted"
    json.dumps(deps.design_attempts)


async def test_unrepairable_json_is_recorded_as_invalid_args(settings: Settings) -> None:
    raw = '{"title": "Regal" "design": {}}'
    async with run_calls(settings, [("save_design", raw)]) as deps:
        [entry] = deps.design_attempts
    assert entry["outcome"] == "invalid_args"
    assert entry["raw_args"] == raw
    assert "Kein gültiges JSON" in entry["errors"][0]


async def test_engine_rejection_is_recorded_with_errors(settings: Settings) -> None:
    async with run_calls(
        settings, [("save_design", {"title": "Regal", "design": below_floor()})]
    ) as deps:
        [entry] = deps.design_attempts
    assert (entry["outcome"], entry["accepted"]) == ("engine_rejected", False)
    assert entry["errors"]
    assert entry["design"]["object_type"] == "Regal"
    assert entry["raw_args"]["title"] == "Regal"
    json.dumps(deps.design_attempts)


async def test_parameter_error_is_recorded(settings: Settings) -> None:
    args = {"command": {"type": "set_parameters", "values": {"width_mm": 999_999_999}}}
    calls: list[tuple[str, str | dict[str, Any]]] = [
        ("save_design", {"title": "Regal", "design": shelf()}),
        ("change_project", args),
    ]
    async with run_calls(settings, calls) as deps:
        _created, entry = deps.design_attempts
    assert entry["tool"] == "change_project"
    assert entry["outcome"] == "parameter_error"
    assert entry["errors"]
    assert entry["raw_args"] == args
    assert entry["design"] is None


async def test_command_and_state_errors_are_recorded(settings: Settings) -> None:
    calls: list[tuple[str, str | dict[str, Any]]] = [
        ("change_project", {"command": {"type": "set_parameters", "values": {"width_mm": 1}}}),
    ]
    async with run_calls(settings, calls) as deps:
        [no_project] = deps.design_attempts
    assert (no_project["tool"], no_project["outcome"]) == ("change_project", "no_project")


async def test_successful_non_design_calls_are_not_recorded(settings: Settings) -> None:
    async with run_calls(settings, [("list_materials", {})]) as deps:
        assert deps.design_attempts == []


async def test_huge_raw_args_are_truncated(settings: Settings) -> None:
    raw = '{"title": "Regal", "design": "' + "x" * (RAW_ARGS_MAX_CHARS + 10) + '"}'
    async with run_calls(settings, [("save_design", raw)]) as deps:
        [entry] = deps.design_attempts
    assert entry["outcome"] == "invalid_args"
    assert len(entry["raw_args"]) < RAW_ARGS_MAX_CHARS + 100
    assert "truncated" in entry["raw_args"]
