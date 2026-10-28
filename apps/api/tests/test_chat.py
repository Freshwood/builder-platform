import json

import httpx
import pytest
from sqlalchemy import select

from homeworking.db.schema import AgentRunRow
from homeworking.modules.agent.offline import ToolCall, decide_for_user_text
from homeworking.modules.pipeline.stages import SkeletonRejectedError, StageUsage


def _message(text: str, message_id: str = "m1") -> dict:  # type: ignore[type-arg]
    return {"id": message_id, "role": "user", "parts": [{"type": "text", "text": text}]}


def _events(raw: str) -> list[dict]:  # type: ignore[type-arg]
    out = []
    for line in raw.splitlines():
        if line.startswith("data: ") and line != "data: [DONE]":
            out.append(json.loads(line[6:]))
    return out


async def _chat(client: httpx.AsyncClient, text: str, project_id: str | None = None) -> list[dict]:  # type: ignore[type-arg]
    body = {"trigger": "submit-message", "id": "c1", "messages": [_message(text)]}
    if project_id:
        body["projectId"] = project_id
    response = await client.post("/api/chat", json=body)
    assert response.status_code == 200, response.text
    return _events(response.text)


def _text(events: list[dict]) -> str:  # type: ignore[type-arg]
    return "".join(e.get("delta", "") for e in events if e.get("type") == "text-delta")


def _tool_outputs(events: list[dict]) -> list[dict]:  # type: ignore[type-arg]
    return [e["output"] for e in events if e.get("type") == "tool-output-available"]


async def test_chat_creates_and_changes_project(client: httpx.AsyncClient) -> None:
    events = await _chat(client, "Ich möchte ein Hochbeet 2 × 1 m, 80 cm hoch, aus Lärche bauen.")
    outputs = _tool_outputs(events)
    assert outputs
    assert outputs[0]["action"] == "created"
    project = outputs[0]["project"]
    assert project["params"]["wood"] == "larch"
    assert "Hochbeet" in _text(events)

    events = await _chat(client, "Mach es 50 cm breiter", project_id=project["project_id"])
    outputs = _tool_outputs(events)
    assert outputs[0]["action"] == "changed"
    assert outputs[0]["diff"]["changed_params"]["width_mm"] == {"before": 1000, "after": 1500}

    stored = (await client.get(f"/api/projects/{project['project_id']}")).json()
    assert stored["project"]["inputs"]["params"]["width_mm"] == 1500


async def test_chat_asks_for_missing_dimensions(client: httpx.AsyncClient) -> None:
    events = await _chat(client, "Ich will ein Hochbeet bauen")
    assert not _tool_outputs(events)
    assert "Wie lang" in _text(events)


async def test_safety_gate_blocks_electrical_work(client: httpx.AsyncClient) -> None:
    events = await _chat(client, "Wie schließe ich eine Steckdose am Hochbeet an 230V an?")
    assert not _tool_outputs(events)
    assert "Elektrofachkräfte" in _text(events)


async def test_change_without_project_reports_error(client: httpx.AsyncClient) -> None:
    events = await _chat(client, "Mach es 50 cm breiter")
    assert "error" in _tool_outputs(events)[0]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Hochbeet 2,4 x 1,2 m, 90 cm hoch",
            {"length_mm": 2400, "width_mm": 1200, "height_mm": 900},
        ),
        (
            "hochbeet 120x80cm höhe 60 cm",
            {"length_mm": 1200, "width_mm": 800, "height_mm": 600},
        ),
        ("Hochbeet 1 × 2 m aus Lärche", {"length_mm": 2000, "width_mm": 1000, "wood": "larch"}),
    ],
)
def test_offline_planner_parses_dimensions(text: str, expected: dict) -> None:  # type: ignore[type-arg]
    decision = decide_for_user_text(text)
    assert isinstance(decision, list)
    assert decision[0].name == "save_design"
    assert decision[0].args["title"] == "Hochbeet"
    assert decision[0].args["params"] == expected
    assert decision[0].args["design"]["object_type"] == "Hochbeet"


def test_offline_planner_relative_change() -> None:
    assert decide_for_user_text("bitte 20 cm niedriger") == [
        ToolCall(
            "change_project",
            {"command": {"type": "change_parameter_by", "name": "height_mm", "delta": -200}},
        )
    ]


async def test_chat_drafts_a_design_offline(client: httpx.AsyncClient) -> None:
    events = await _chat(client, "Ich brauche ein Regal 100 x 35 x 200 cm mit 6 Böden")
    outputs = _tool_outputs(events)
    assert outputs[0]["action"] == "created"
    project = outputs[0]["project"]
    assert "trust" not in project
    assert project["params"]["width_mm"] == 1000
    assert project["params"]["shelves"] == 6

    events = await _chat(client, "Bitte 20 cm breiter", project["project_id"])
    outputs = _tool_outputs(events)
    assert outputs[0]["diff"]["changed_params"]["width_mm"] == {"before": 1000, "after": 1200}


def test_offline_planner_only_drafts_what_it_knows() -> None:
    """Without a language model there are no templates to fall back on (ADR-0008)."""
    decision = decide_for_user_text("Werkbank 150 x 70 cm mit Rollen")
    assert isinstance(decision, str)


async def test_chat_plans_a_new_design_through_the_pipeline(client: httpx.AsyncClient) -> None:
    events = await _chat(client, "Ich brauche einen Schrank 80 x 40 x 100 cm, drinnen")
    outputs = _tool_outputs(events)
    assert outputs[0]["action"] == "created"
    project = outputs[0]["project"]
    assert project["params"]["width_mm"] == 800

    stored = (await client.get(f"/api/projects/{project['project_id']}")).json()
    design = stored["project"]["inputs"]["design"]
    assert {p["id"] for p in design["parts"]} == {
        "body_left",
        "body_right",
        "body_bottom",
        "body_top",
    }
    assert [s["title"] for s in design["steps"]] == ["Korpus"]
    notes = stored["project"]["inputs"]["notes"]
    assert any("Korpus besteht aus Platten" in n["text"] for n in notes)

    container = client._transport.app.state.container  # type: ignore[attr-defined]
    async with container.sessions() as session:
        runs = (await session.scalars(select(AgentRunRow))).all()
    stages = sorted(r.routing_reason for r in runs if r.routing_reason.startswith("stage:"))
    assert stages == ["stage:docs", "stage:modules", "stage:skeleton"]
    assert {r.chat_id for r in runs} == {"c1"}


async def test_planning_without_a_size_is_not_attempted(client: httpx.AsyncClient) -> None:
    events = await _chat(client, "Ich brauche einen Schrank")
    assert not _tool_outputs(events)


async def test_a_rejected_plan_is_reported_to_the_model(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = client._transport.app.state.container  # type: ignore[attr-defined]

    async def rejected(spec: object, *, on_stage: object = None) -> object:
        raise SkeletonRejectedError(["Parameter 'x' fehlt"], StageUsage("skeleton"))

    monkeypatch.setattr(container.pipeline, "design", rejected)
    events = await _chat(client, "Ich brauche einen Schrank 80 x 40 x 100 cm")
    (output,) = _tool_outputs(events)
    assert "nicht gelungen" in output["error"]
    assert output["errors"] == ["Parameter 'x' fehlt"]
    assert (await client.get("/api/projects")).json() == []


async def test_a_provider_error_in_the_pipeline_is_explained_not_raised(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = client._transport.app.state.container  # type: ignore[attr-defined]

    async def broken(spec: object, *, on_stage: object = None) -> object:
        raise RuntimeError("provider down")

    monkeypatch.setattr(container.pipeline, "design", broken)
    events = await _chat(client, "Ich brauche einen Schrank 80 x 40 x 100 cm")
    (output,) = _tool_outputs(events)
    assert output["errors"] == ["Modellaufruf fehlgeschlagen: RuntimeError"]


async def test_a_failing_brief_is_not_planned_again_and_again() -> None:
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    from construction_model.pipeline import Spec
    from homeworking.modules.agent.tools import AgentDeps, PlanFailedError, build_agent

    runs: list[Spec] = []

    class Failing:
        async def plan(self, spec: Spec) -> object:
            runs.append(spec)
            raise PlanFailedError(["kaputt"])

    calls = {"n": 0}
    spec = {"description": "Schrank", "width_mm": 800, "depth_mm": 400, "height_mm": 1000}

    def script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls["n"] += 1
        if calls["n"] > 3:
            return ModelResponse(parts=[TextPart("Es hat nicht geklappt.")])
        return ModelResponse(
            parts=[ToolCallPart("plan_design", {"spec": spec, "title": "Schrank"})]
        )

    agent: Agent[AgentDeps, str] = build_agent(FunctionModel(script))
    deps = AgentDeps(
        owner_id=None,  # type: ignore[arg-type]
        projects=None,  # type: ignore[arg-type]
        project_id=None,
        trace_id="t",
        planner=Failing(),  # type: ignore[arg-type]
    )
    await agent.run("Schrank 80 x 40 x 100", deps=deps)
    assert len(runs) == 2  # the third call is refused without a pipeline run
    outcomes = [a["outcome"] for a in deps.design_attempts]
    assert outcomes == ["engine_rejected", "engine_rejected", "plan_limit"]
