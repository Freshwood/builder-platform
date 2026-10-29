"""Failure paths of the stage and chat endpoints: a provider error or timeout still stores the run
(AI results cost money) and ends in a 4xx the client can show, never in a bare 500 without a row."""

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import select

from homeworking.api.pipeline import MODEL_FAILED_MESSAGE
from homeworking.bootstrap import build_container
from homeworking.construction_model.pipeline import Skeleton, Spec
from homeworking.db.schema import AgentRunRow
from homeworking.main import create_app
from homeworking.modules.agent.deps import PlanFailedError
from homeworking.modules.agent.planner import ChatPlanner
from homeworking.modules.pipeline.stages import (
    ModulesRejectedError,
    Pipeline,
    SkeletonRejectedError,
    StageFailedError,
    StageUsage,
)
from homeworking.settings import Settings

BRIEF = "Regal 80 x 30 x 180 cm, drinnen, an der Wand"
SPEC = Spec(description="Regal", width_mm=800, depth_mm=300, height_mm=1800)
SPEC_JSON = {"description": "Regal", "width_mm": 800, "depth_mm": 300, "height_mm": 1800}


def _length(name: str, value: int) -> dict[str, Any]:
    return {
        "name": name,
        "label": name,
        "kind": "length",
        "default": value,
        "min": 100,
        "max": 3000,
    }


def _good_skeleton() -> dict[str, Any]:
    return {
        "object_type": "Regal",
        "summary": "Regal",
        "params": [_length("width_mm", 800), _length("depth_mm", 300), _length("height_mm", 1800)],
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


def _bad_skeleton() -> dict[str, Any]:
    good = _good_skeleton()
    return {**good, "modules": [{**good["modules"][0], "size": ["nope", 10, 10]}]}


def _provider_down() -> Exception:
    return ModelHTTPError(503, "scripted", {"error": "overloaded"})


def _failing(error: Callable[[], Exception]) -> FunctionModel:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise error()

    return FunctionModel(respond, model_name="failing")


def _scripted(*answers: dict[str, Any] | Exception) -> FunctionModel:
    """Answers (or errors to raise) in call order."""
    queue = list(answers)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        answer = queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, answer)])

    return FunctionModel(respond, model_name="scripted")


def _pipeline(**models: Model) -> Pipeline:
    return Pipeline(Settings(llm_mode="test"), None, {"spruce": "Fichte"}, **models)  # type: ignore[arg-type]


async def _client(settings: Settings, pipeline: Pipeline) -> AsyncIterator[httpx.AsyncClient]:
    container = build_container(settings)
    container.pipeline = pipeline
    app = create_app(settings, container, create_schema=True)
    async with app.router.lifespan_context(app):
        # A bug must show up as a 500 response, not as an exception in the test client.
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def _runs(client: httpx.AsyncClient) -> list[AgentRunRow]:
    container = client._transport.app.state.container  # type: ignore[attr-defined]
    async with container.sessions() as session:
        return list((await session.scalars(select(AgentRunRow))).all())


@pytest.fixture
async def intake_down(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    async for client in _client(settings, _pipeline(intake_model=_failing(_provider_down))):
        yield client


@pytest.fixture
async def skeleton_down(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    # The first request is answered (but the engine rejects it), the repair request times out.
    model = _scripted(_bad_skeleton(), TimeoutError("read timed out"))
    async for client in _client(settings, _pipeline(skeleton_model=model)):
        yield client


@pytest.fixture
async def modules_down(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    async for client in _client(settings, _pipeline(module_model=_failing(_provider_down))):
        yield client


# --- stage endpoints ---------------------------------------------------------------------------


async def test_a_provider_error_in_intake_is_a_stored_422(intake_down: httpx.AsyncClient) -> None:
    response = await intake_down.post("/api/pipeline/intake", json={"spec": {"description": BRIEF}})
    assert response.status_code == 422
    assert response.json()["detail"] == MODEL_FAILED_MESSAGE
    (run,) = await _runs(intake_down)
    assert run.status == "failed"
    assert run.routing_reason == "stage:intake"
    assert "ModelHTTPError" in (run.error or "")
    assert run.prompt_fingerprint
    assert run.usage is not None
    assert run.usage["requests"] == 0


async def test_intake_without_a_model_call_does_not_fail_when_the_model_is_down(
    intake_down: httpx.AsyncClient,
) -> None:
    response = await intake_down.post(
        "/api/pipeline/intake",
        json={"spec": {"description": "Regal", "width_mm": 800}, "extract": False},
    )
    assert response.status_code == 200
    assert await _runs(intake_down) == []


async def test_a_timeout_in_the_skeleton_stage_stores_the_usage_so_far(
    skeleton_down: httpx.AsyncClient,
) -> None:
    response = await skeleton_down.post("/api/pipeline/skeleton", json={"spec": SPEC_JSON})
    assert response.status_code == 422
    assert response.json()["detail"] == MODEL_FAILED_MESSAGE
    (run,) = await _runs(skeleton_down)
    assert run.status == "failed"
    assert run.routing_reason == "stage:skeleton"
    assert run.model_role == "designer"
    assert "TimeoutError" in (run.error or "")
    assert run.usage is not None
    assert run.usage["requests"] == 1  # the first request was answered, the second timed out
    assert run.duration_ms is not None


async def test_a_provider_error_in_the_modules_stage_is_a_stored_422(
    modules_down: httpx.AsyncClient,
) -> None:
    skeleton = Skeleton.model_validate(_good_skeleton()).model_dump(mode="json")
    response = await modules_down.post(
        "/api/pipeline/modules", json={"spec": SPEC_JSON, "skeleton": skeleton}
    )
    assert response.status_code == 422
    assert response.json()["detail"] == MODEL_FAILED_MESSAGE
    (run,) = await _runs(modules_down)
    assert (run.status, run.routing_reason) == ("failed", "stage:modules")
    assert "ModelHTTPError" in (run.error or "")


async def test_an_unusable_intake_answer_is_a_stored_422(settings: Settings) -> None:
    # Invalid output after the framework's retries (UnexpectedModelBehavior) fails the stage.
    model = _scripted({"updates": "no"}, {"updates": "no"}, {"updates": "no"})
    async for client in _client(settings, _pipeline(intake_model=model)):
        response = await client.post("/api/pipeline/intake", json={"spec": {"description": BRIEF}})
        assert response.status_code == 422
        (run,) = await _runs(client)
        assert run.status == "failed"
        assert "UnexpectedModelBehavior" in (run.error or "")


async def test_a_storage_problem_does_not_hide_the_422(
    skeleton_down: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = skeleton_down._transport.app.state.container  # type: ignore[attr-defined]

    async def broken(run: object) -> None:
        raise RuntimeError("database is gone")

    monkeypatch.setattr(container.conversations, "record", broken)
    response = await skeleton_down.post("/api/pipeline/skeleton", json={"spec": SPEC_JSON})
    assert response.status_code == 422


async def test_a_rejected_skeleton_is_still_stored_as_failed(settings: Settings) -> None:
    model = _scripted(_bad_skeleton(), _bad_skeleton())
    async for client in _client(settings, _pipeline(skeleton_model=model)):
        response = await client.post("/api/pipeline/skeleton", json={"spec": SPEC_JSON})
        assert response.status_code == 422
        assert response.json()["detail"] != MODEL_FAILED_MESSAGE
        (run,) = await _runs(client)
        assert (run.status, run.usage["requests"]) == ("failed", 2)  # type: ignore[index]


# --- the stages themselves ---------------------------------------------------------------------


async def test_a_failed_model_call_carries_the_usage_so_far() -> None:
    pipeline = _pipeline(skeleton_model=_scripted(_bad_skeleton(), _provider_down()))
    with pytest.raises(StageFailedError) as raised:
        await pipeline.skeleton(SPEC)
    assert raised.value.usage.requests == 1
    assert raised.value.usage.duration_ms >= 0
    assert isinstance(raised.value.cause, ModelHTTPError)


async def test_a_failing_module_call_ends_the_modules_stage() -> None:
    first = _good_skeleton()
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
    with pytest.raises(StageFailedError) as raised:
        await _pipeline(module_model=_failing(_provider_down)).modules(
            SPEC, Skeleton.model_validate(two)
        )
    assert raised.value.usage.stage == "modules"


async def test_design_reports_a_failed_stage_to_the_recorder() -> None:
    seen: list[tuple[str, str | None]] = []

    async def record(usage: StageUsage, error: str | None) -> None:
        seen.append((usage.stage, error))

    pipeline = _pipeline(module_model=_failing(_provider_down))
    with pytest.raises(StageFailedError):
        await pipeline.design(SPEC, on_stage=record)
    assert [stage for stage, _ in seen] == ["skeleton", "modules"]
    assert "ModelHTTPError" in (seen[1][1] or "")


async def test_the_design_survives_a_failing_documentation_model() -> None:
    built = await _pipeline().modules(SPEC, Skeleton.model_validate(_good_skeleton()))
    docs = await _pipeline(docs_model=_failing(_provider_down)).document(
        SPEC, Skeleton.model_validate(_good_skeleton()), built
    )
    assert docs.explanation is None
    assert docs.error is not None
    assert "ModelHTTPError" in docs.error
    (step,) = docs.design.steps
    assert (step.title, step.text) == ("Korpus", "Korpus")

    seen: list[tuple[str, str | None]] = []

    async def record(usage: StageUsage, error: str | None) -> None:
        seen.append((usage.stage, error))

    result = await _pipeline(docs_model=_failing(_provider_down)).design(SPEC, on_stage=record)
    assert result.design.steps
    assert seen[-1][0] == "docs"
    assert seen[-1][1] is not None


# --- ChatPlanner: how stage failures reach the chat model ----------------------------------------


def _planner(pipeline: Pipeline, text: str = "") -> ChatPlanner:
    container = build_container(Settings(llm_mode="test"))
    container.pipeline = pipeline
    return ChatPlanner(container.pipeline, container.conversations, None, None, text)  # type: ignore[arg-type]


async def test_planner_reports_a_blocked_brief_as_the_safety_message() -> None:
    planner = _planner(_pipeline())
    with pytest.raises(PlanFailedError) as raised:
        await planner.plan(Spec(description="Ich will eine neue Steckdose und Elektroinstallation"))
    assert "Elektrofachkräfte" in raised.value.errors[0]


async def test_planner_maps_a_rejected_skeleton_to_the_engines_problems(
    settings: Settings,
) -> None:
    model = _scripted(_bad_skeleton(), _bad_skeleton())
    async for client in _client(settings, _pipeline(skeleton_model=model)):
        container = client._transport.app.state.container  # type: ignore[attr-defined]
        owner = (await container.identity.create_guest()).id
        with pytest.raises(PlanFailedError) as raised:
            await ChatPlanner(
                container.pipeline, container.conversations, owner, "chat-1", ""
            ).plan(SPEC)
        assert any("size x" in error for error in raised.value.errors)
        assert isinstance(raised.value.__cause__, SkeletonRejectedError)
        (run,) = await _runs(client)
        assert (run.status, run.routing_reason) == ("failed", "stage:skeleton")


async def test_planner_maps_rejected_modules_to_one_line_per_problem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline = _pipeline()

    async def rejected(spec: Spec, **_: object) -> object:
        raise ModulesRejectedError({"body": ["a", "b"], "side": ["c"]}, StageUsage("modules"))

    monkeypatch.setattr(pipeline, "design", rejected)
    with pytest.raises(PlanFailedError) as raised:
        await _planner(pipeline).plan(SPEC)
    assert raised.value.errors == ["body: a", "body: b", "side: c"]


async def test_planner_maps_a_provider_error_and_stores_the_failed_stage(
    settings: Settings,
) -> None:
    async for client in _client(settings, _pipeline(skeleton_model=_failing(_provider_down))):
        container = client._transport.app.state.container  # type: ignore[attr-defined]
        owner = (await container.identity.create_guest()).id
        planner = ChatPlanner(container.pipeline, container.conversations, owner, "chat-1", "")
        with pytest.raises(PlanFailedError) as raised:
            await planner.plan(SPEC)
        assert raised.value.errors == ["Modellaufruf fehlgeschlagen: ModelHTTPError"]
        (run,) = await _runs(client)
        assert (run.status, run.chat_id, run.routing_reason) == (
            "failed",
            "chat-1",
            "stage:skeleton",
        )


async def test_planner_maps_any_other_error_by_its_type(monkeypatch: pytest.MonkeyPatch) -> None:
    pipeline = _pipeline()

    async def broken(spec: Spec, **_: object) -> object:
        raise ZeroDivisionError

    monkeypatch.setattr(pipeline, "design", broken)
    with pytest.raises(PlanFailedError) as raised:
        await _planner(pipeline).plan(SPEC)
    assert raised.value.errors == ["Modellaufruf fehlgeschlagen: ZeroDivisionError"]


# --- chat endpoint -----------------------------------------------------------------------------


def _chat_body(text: str = "Hallo") -> dict[str, Any]:
    message = {"id": "m1", "role": "user", "parts": [{"type": "text", "text": text}]}
    return {"trigger": "submit-message", "id": "c1", "messages": [message]}


@pytest.mark.parametrize(
    "raw",
    [b"{not json", b"[]", b'"text"', b'{"messages": "no"}', b'{"messages": [{"role": "robot"}]}'],
)
async def test_a_malformed_chat_body_is_a_422(client: httpx.AsyncClient, raw: bytes) -> None:
    response = await client.post(
        "/api/chat", content=raw, headers={"content-type": "application/json"}
    )
    assert response.status_code == 422
    assert "ungültig" in response.json()["detail"]
    assert await _runs(client) == []


async def test_a_failing_history_still_stores_the_turn(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    async for client in _client(settings, _pipeline()):
        container = client._transport.app.state.container  # type: ignore[attr-defined]

        async def broken(*args: object, **kwargs: object) -> list[Any]:
            raise RuntimeError("history is gone")

        monkeypatch.setattr(container.conversations, "history", broken)
        response = await client.post("/api/chat", json=_chat_body("Ich brauche ein Regal"))
        assert response.status_code == 500
        (run,) = await _runs(client)
        assert run.status == "failed"
        assert "RuntimeError: history is gone" in (run.error or "")
        assert run.chat_id == "c1"
        assert [m["role"] for m in run.ui_messages] == ["user", "assistant"]
        assert run.ui_messages[0]["parts"][0]["text"] == "Ich brauche ein Regal"
        assert run.model == ""
        json.dumps(run.usage)


async def test_a_failing_fingerprint_still_stores_the_turn(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    async for client in _client(settings, _pipeline()):

        async def broken() -> str:
            raise RuntimeError("no fingerprint")

        monkeypatch.setattr("homeworking.api.chat.prompt_fingerprint", broken)
        response = await client.post("/api/chat", json=_chat_body())
        assert response.status_code == 500
        (run,) = await _runs(client)
        assert (run.status, run.error) == ("failed", "RuntimeError: no fingerprint")


async def test_a_failed_turn_never_stores_personal_data(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    async for client in _client(settings, _pipeline()):
        container = client._transport.app.state.container  # type: ignore[attr-defined]

        async def broken(*args: object, **kwargs: object) -> list[Any]:
            raise RuntimeError("history is gone")

        monkeypatch.setattr(container.conversations, "history", broken)
        await client.post(
            "/api/chat",
            json=_chat_body("Mail mich an erika.mustermann@example.com wegen des Regals"),
        )
        (run,) = await _runs(client)
        assert "erika.mustermann@example.com" not in json.dumps(run.ui_messages)
