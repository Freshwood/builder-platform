"""Intake and skeleton endpoints (ADR-0010), offline."""

from typing import Any

import httpx
import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import select

from construction_model.pipeline import Skeleton, Spec
from homeworking.db.schema import AgentRunRow
from homeworking.modules.pipeline.stages import Pipeline, SkeletonRejectedError
from homeworking.settings import Settings

BRIEF = "Regal 80 x 30 x 180 cm, drinnen, an der Wand"


async def _runs(client: httpx.AsyncClient) -> list[AgentRunRow]:
    container = client._transport.app.state.container  # type: ignore[attr-defined]
    async with container.sessions() as session:
        return list((await session.scalars(select(AgentRunRow))).all())


async def test_intake_reads_the_text_and_asks_only_what_is_open(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/pipeline/intake", json={"spec": {"description": BRIEF}})
    assert response.status_code == 200
    body = response.json()
    assert body["spec"]["width_mm"] == 800
    assert body["spec"]["height_mm"] == 1800
    assert body["spec"]["use"] == "indoor"
    assert body["spec"]["support"] == "wall"
    assert body["ready"] is True
    asked = [q["field"] for q in body["questions"]]
    assert "size" not in asked
    assert "use" not in asked
    assert len(asked) <= 3


async def test_intake_without_size_blocks_and_asks_for_it_first(client: httpx.AsyncClient) -> None:
    body = (
        await client.post("/api/pipeline/intake", json={"spec": {"description": "Ein Regal"}})
    ).json()
    assert body["ready"] is False
    assert body["questions"][0]["field"] == "size"
    assert body["questions"][0]["blocking"] is True


async def test_no_model_call_when_nothing_is_open(client: httpx.AsyncClient) -> None:
    spec = {
        "description": "Regal",
        "width_mm": 800,
        "depth_mm": 300,
        "height_mm": 1800,
        "use": "indoor",
        "support": "floor",
        "wood": "spruce",
        "finish": "oil",
        "experience": "advanced",
    }
    body = (await client.post("/api/pipeline/intake", json={"spec": spec})).json()
    assert body["questions"] == []
    assert body["usage"]["requests"] == 0
    assert await _runs(client) == []


async def test_answers_are_recomputed_without_a_model_call(client: httpx.AsyncClient) -> None:
    body = (
        await client.post(
            "/api/pipeline/intake",
            json={"spec": {"description": "Regal", "width_mm": 800}, "extract": False},
        )
    ).json()
    assert body["usage"]["requests"] == 0
    assert body["ready"] is True


async def test_intake_run_is_stored_with_usage_and_fingerprint(client: httpx.AsyncClient) -> None:
    await client.post("/api/pipeline/intake", json={"spec": {"description": BRIEF}})
    (run,) = await _runs(client)
    assert run.routing_reason == "stage:intake"
    assert run.model_role == "fast"
    assert run.prompt_fingerprint
    assert run.usage is not None
    assert run.usage["requests"] == 1


async def test_skeleton_carries_the_customers_facts(client: httpx.AsyncClient) -> None:
    intake = (
        await client.post("/api/pipeline/intake", json={"spec": {"description": BRIEF}})
    ).json()
    response = await client.post("/api/pipeline/skeleton", json={"spec": intake["spec"]})
    assert response.status_code == 200
    skeleton = Skeleton.model_validate(response.json()["skeleton"])
    assert skeleton.use == "indoor"
    assert skeleton.support == "wall"
    height = next(p for p in skeleton.params if p.name == "height_mm")
    assert height.default == 1800
    assert {r.routing_reason for r in await _runs(client)} == {"stage:intake", "stage:skeleton"}


async def test_skeleton_needs_a_size(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/pipeline/skeleton", json={"spec": {"description": "Regal"}})
    assert response.status_code == 409


async def test_safety_gate_applies_to_the_stages(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/pipeline/intake",
        json={"spec": {"description": "Ich will eine neue Steckdose und Elektroinstallation"}},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["blocked"] is True
    assert await _runs(client) == []


async def test_unknown_spec_fields_are_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/pipeline/intake", json={"spec": {"description": "x", "color": "red"}}
    )
    assert response.status_code == 422


# --- skeleton repair loop -------------------------------------------------------------------


def _pipeline(*answers: dict[str, Any]) -> tuple[Pipeline, list[list[ModelMessage]]]:
    seen: list[list[ModelMessage]] = []
    queue = list(answers)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(list(messages))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, queue.pop(0))])

    pipeline = Pipeline(
        Settings(llm_mode="test"),
        None,  # type: ignore[arg-type]
        {"spruce": "Fichte"},
        skeleton_model=FunctionModel(respond, model_name="scripted"),
    )
    return pipeline, seen


def _good() -> dict[str, Any]:
    def length(name: str, value: int) -> dict[str, Any]:
        return {
            "name": name,
            "label": name,
            "kind": "length",
            "default": value,
            "min": 100,
            "max": 3000,
        }

    return {
        "object_type": "Regal",
        "summary": "Regal",
        "params": [length("width_mm", 800), length("depth_mm", 300), length("height_mm", 1800)],
        "modules": [
            {
                "id": "body",
                "title": "Korpus",
                "role": "Korpus",
                "origin": [0, 0, 0],
                "size": ["width_mm", "depth_mm", "height_mm"],
            }
        ],
    }


async def test_skeleton_is_repaired_once_with_the_engines_problems() -> None:
    spec = Spec(description="Regal", width_mm=800, depth_mm=300, height_mm=1800)
    good = _good()
    bad = {**good, "modules": [{**good["modules"][0], "size": ["nope", 10, 10]}]}
    pipeline, seen = _pipeline(bad, good)
    result = await pipeline.skeleton(spec)
    assert len(result.attempts) == 1
    assert "size x" in result.attempts[0][0]
    assert len(seen) == 2
    assert "Korrigiere genau diese Fehler" in str(seen[1][-1])


async def test_skeleton_gives_up_after_two_attempts() -> None:
    spec = Spec(description="Regal", width_mm=800, depth_mm=300, height_mm=1800)
    good = _good()
    bad = {**good, "modules": [{**good["modules"][0], "size": ["nope", 10, 10]}]}
    pipeline, _ = _pipeline(bad, bad)
    with pytest.raises(SkeletonRejectedError) as raised:
        await pipeline.skeleton(spec)
    assert raised.value.usage.requests == 2
