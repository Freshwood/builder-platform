"""Intake, skeleton and module endpoints (ADR-0010), offline."""

from typing import Any

import httpx
import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import select

from calc_engine.pipeline.merge import SKELETON
from construction_model.pipeline import Skeleton, Spec
from homeworking.db.schema import AgentRunRow
from homeworking.modules.pipeline import offline
from homeworking.modules.pipeline.stages import (
    ModulesRejectedError,
    Pipeline,
    SkeletonRejectedError,
    StageUsage,
)
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


# --- modules --------------------------------------------------------------------------------


async def test_modules_endpoint_returns_a_design_the_engine_accepts(
    client: httpx.AsyncClient,
) -> None:
    intake = (
        await client.post("/api/pipeline/intake", json={"spec": {"description": BRIEF}})
    ).json()
    skeleton = (await client.post("/api/pipeline/skeleton", json={"spec": intake["spec"]})).json()
    response = await client.post(
        "/api/pipeline/modules", json={"spec": intake["spec"], "skeleton": skeleton["skeleton"]}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["repairs"] == 0
    assert {p["id"] for p in body["design"]["parts"]} == {
        "body_left",
        "body_right",
        "body_bottom",
        "body_top",
    }
    assert body["design"]["support"] == "wall"
    assert body["usage"]["requests"] == 1
    runs = {r.routing_reason: r for r in await _runs(client)}
    assert runs["stage:modules"].model_role == "fast"
    assert runs["stage:modules"].status == "completed"


async def test_modules_need_a_size(client: httpx.AsyncClient) -> None:
    spec = {"description": "Regal"}
    skeleton = Skeleton.model_validate(_good()).model_dump(mode="json")
    response = await client.post("/api/pipeline/modules", json={"spec": spec, "skeleton": skeleton})
    assert response.status_code == 409


async def test_a_skeleton_the_engine_rejects_costs_no_model_call(client: httpx.AsyncClient) -> None:
    good = _good()
    bad = {**good, "modules": [{**good["modules"][0], "size": ["nope", 10, 10]}]}
    skeleton = Skeleton.model_validate(bad).model_dump(mode="json")
    spec = {"description": "Regal", "width_mm": 800, "depth_mm": 300, "height_mm": 1800}
    response = await client.post("/api/pipeline/modules", json={"spec": spec, "skeleton": skeleton})
    assert response.status_code == 422
    assert "skeleton" in response.json()["detail"]
    assert await _runs(client) == []


def _module_pipeline(
    *answers: dict[str, Any] | None,
) -> tuple[Pipeline, list[list[ModelMessage]]]:
    """Scripted module answers in call order; ``None`` means the offline carcass."""
    seen: list[list[ModelMessage]] = []
    queue = list(answers)
    fallback = offline.module_model().function

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(list(messages))
        answer = queue.pop(0) if queue else None
        if answer is None:
            return fallback(messages, info)  # type: ignore[return-value, misc]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, answer)])

    pipeline = Pipeline(
        Settings(llm_mode="test"),
        None,  # type: ignore[arg-type]
        {"spruce": "Fichte"},
        module_model=FunctionModel(respond, model_name="scripted"),
    )
    return pipeline, seen


SPEC = Spec(description="Regal", width_mm=800, depth_mm=300, height_mm=1800)


def _skeleton() -> Skeleton:
    return Skeleton.model_validate(_good())


async def test_a_module_the_engine_rejects_is_repaired_with_its_own_ids() -> None:
    part = {
        "id": "left",
        "name": "Seite",
        "material": "no_such_material",
        "size": [18, 300, 1800],
        "at": [0, 0, 0],
    }
    pipeline, seen = _module_pipeline({"module": "body", "parts": [part]})
    result = await pipeline.modules(SPEC, _skeleton())
    assert len(result.repairs) == 1
    assert set(result.repairs[0]) == {"body"}
    assert len(seen) == 2
    repair = str(seen[1][-1])
    assert "Korrigiere genau diese Fehler" in repair
    assert "'left[0]'" in repair  # the module's id, not the merged 'body_left'
    assert "list_materials" not in repair
    assert "body_left" not in repair
    assert result.usage.requests == 2


async def test_modules_give_up_after_the_repair_rounds() -> None:
    part = {
        "id": "left",
        "name": "Seite",
        "material": "no_such_material",
        "size": [18, 300, 1800],
        "at": [0, 0, 0],
    }
    bad = {"module": "body", "parts": [part]}
    pipeline, seen = _module_pipeline(bad, bad, bad)
    with pytest.raises(ModulesRejectedError) as raised:
        await pipeline.modules(SPEC, _skeleton())
    assert set(raised.value.errors) == {"body"}
    assert len(seen) == 3  # first run plus two repairs


async def test_an_invalid_module_answer_is_asked_again_from_the_start() -> None:
    broken = {"module": "body", "parts": []}  # a module needs at least one part
    pipeline, seen = _module_pipeline(broken, broken, None)
    result = await pipeline.modules(SPEC, _skeleton())
    assert len(result.repairs) == 1
    assert "fehlt" in result.repairs[0]["body"][0]
    assert "Die letzte Antwort war ungültig" in str(seen[-1][0])
    assert {p.id for p in result.design.parts} == {
        "body_left",
        "body_right",
        "body_bottom",
        "body_top",
    }


async def test_only_the_blamed_module_runs_again() -> None:
    first = _good()
    two = {
        **first,
        "modules": [
            {**first["modules"][0], "id": "left", "size": [400, "depth_mm", "height_mm"]},
            {
                **first["modules"][0],
                "id": "right",
                "origin": [400, 0, 0],
                "size": [400, "depth_mm", "height_mm"],
            },
        ],
    }
    skeleton = Skeleton.model_validate(two)
    bad = {
        "module": "right",
        "parts": [
            {
                "id": "x",
                "name": "Teil",
                "material": "no_such_material",
                "size": [18, 300, 1800],
                "at": [0, 0, 0],
            }
        ],
    }
    # Calls run in module order: left (offline), right (bad); the repair re-runs only 'right'.
    pipeline, seen = _module_pipeline(None, bad)
    result = await pipeline.modules(SPEC, skeleton)
    assert set(result.repairs[0]) == {"right"}
    assert len(seen) == 3
    assert result.usage.requests == 3


# --- docs and the whole design ----------------------------------------------------------------


def _docs_pipeline(answer: dict[str, Any]) -> Pipeline:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, answer)])

    return Pipeline(
        Settings(llm_mode="test"),
        None,  # type: ignore[arg-type]
        {"spruce": "Fichte"},
        docs_model=FunctionModel(respond, model_name="scripted"),
    )


async def test_design_runs_all_stages_and_reports_each_to_the_recorder() -> None:
    seen: list[tuple[str, str | None]] = []

    async def record(usage: StageUsage, error: str | None) -> None:
        seen.append((usage.stage, error))

    result = await Pipeline(Settings(llm_mode="test"), None, {"spruce": "Fichte"}).design(
        SPEC, on_stage=record
    )  # type: ignore[arg-type]
    assert seen == [("skeleton", None), ("modules", None), ("docs", None)]
    assert [s.stage for s in result.stages] == ["skeleton", "modules", "docs"]
    assert result.explanation
    (step,) = result.design.steps
    assert set(step.parts) == {p.id for p in result.design.parts}


async def test_a_failing_stage_is_still_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, str | None]] = []

    async def record(usage: StageUsage, error: str | None) -> None:
        seen.append((usage.stage, error))

    pipeline = Pipeline(Settings(llm_mode="test"), None, {"spruce": "Fichte"})  # type: ignore[arg-type]

    async def rejected(spec: Spec, skeleton: Skeleton) -> object:
        usage = StageUsage("modules", requests=3)
        raise ModulesRejectedError({"body": ["kaputt"]}, usage)

    monkeypatch.setattr(pipeline, "modules", rejected)
    with pytest.raises(ModulesRejectedError):
        await pipeline.design(SPEC, on_stage=record)
    assert [stage for stage, _ in seen] == ["skeleton", "modules"]
    assert "kaputt" in (seen[1][1] or "")


async def test_the_design_survives_an_unusable_documentation() -> None:
    built = await Pipeline(Settings(llm_mode="test"), None, {"spruce": "Fichte"}).modules(  # type: ignore[arg-type]
        SPEC, _skeleton()
    )
    # The model never delivers a valid answer (empty explanation): steps fall back to the briefs.
    broken = _docs_pipeline({"explanation": "", "steps": []})
    docs = await broken.document(SPEC, _skeleton(), built)
    assert docs.explanation is None
    (step,) = docs.design.steps
    assert (step.title, step.text) == ("Korpus", "Korpus")
    assert set(step.parts) == {p.id for p in docs.design.parts}


async def test_a_skeleton_error_of_the_merge_revises_the_skeleton_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Errors no module owns go back to the skeleton stage, then all modules run again."""
    skeleton_prompts: list[str] = []
    answers = [_good(), _good()]

    def plan(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        skeleton_prompts.append(str(messages[-1]))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, answers.pop(0))])

    pipeline = Pipeline(
        Settings(llm_mode="test"),
        None,  # type: ignore[arg-type]
        {"spruce": "Fichte"},
        skeleton_model=FunctionModel(plan, model_name="scripted"),
    )
    real = pipeline.modules
    calls: list[int] = []

    async def modules(spec: Spec, skeleton: Skeleton) -> Any:
        calls.append(1)
        if len(calls) == 1:
            raise ModulesRejectedError(
                {SKELETON: ["Der Entwurf ist zu hoch"]}, StageUsage("modules")
            )
        return await real(spec, skeleton)

    monkeypatch.setattr(pipeline, "modules", modules)
    seen: list[tuple[str, str | None]] = []

    async def record(usage: StageUsage, error: str | None) -> None:
        seen.append((usage.stage, error))

    result = await pipeline.design(SPEC, on_stage=record)
    assert len(calls) == 2
    assert "Korrigiere genau diese Fehler" in skeleton_prompts[1]
    assert "Der Entwurf ist zu hoch" in skeleton_prompts[1]
    assert [s.stage for s in result.stages] == [
        "skeleton",
        "modules",
        "skeleton",
        "modules",
        "docs",
    ]


async def test_a_second_skeleton_error_ends_the_design(monkeypatch: pytest.MonkeyPatch) -> None:
    pipeline = Pipeline(Settings(llm_mode="test"), None, {"spruce": "Fichte"})  # type: ignore[arg-type]

    async def modules(spec: Spec, skeleton: Skeleton) -> Any:
        raise ModulesRejectedError({SKELETON: ["zu hoch"]}, StageUsage("modules", requests=2))

    monkeypatch.setattr(pipeline, "modules", modules)
    with pytest.raises(ModulesRejectedError):
        await pipeline.design(SPEC)


async def test_skeleton_output_the_model_cannot_deliver_counts_as_a_failed_attempt() -> None:
    # {} violates the schema twice (the framework retries once), then a valid answer follows.
    pipeline, seen = _pipeline({}, {}, _good())
    result = await pipeline.skeleton(SPEC)
    assert len(result.attempts) == 1
    assert "Ausgabe unbrauchbar" in result.attempts[0][0]
    assert len(seen) == 3


async def test_module_prompt_describes_bool_parameters() -> None:
    skeleton = Skeleton.model_validate(
        {
            **_good(),
            "params": [
                *_good()["params"],
                {"name": "back_panel", "label": "Rückwand", "kind": "bool", "default": True},
            ],
        }
    )
    pipeline, seen = _module_pipeline()
    await pipeline.modules(SPEC, skeleton)
    assert "back_panel=True (bool)" in str(seen[0][0])
