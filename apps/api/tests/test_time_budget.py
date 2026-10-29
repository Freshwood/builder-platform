"""The time budget of a design: fixed values per category, and a pipeline that respects them.

Offline tests cannot measure a real model, so they prove the mechanism with deliberately slow
stand-ins: a stage that would take seconds must end at the deadline, not when the model answers.
The real durations are measured by ``task eval:live`` against the same values.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from homeworking.calc_engine.pipeline.budget import (
    HEAVY_FROM_MM,
    TIME_BUDGET_S,
    classify,
    time_budget_s,
)
from homeworking.construction_model.pipeline import Spec
from homeworking.modules.agent.planner import CHAT_RESERVE_S, ChatPlanner
from homeworking.modules.pipeline import offline
from homeworking.modules.pipeline.stages import (
    DeadlineExceededError,
    ModulesRejectedError,
    Pipeline,
    StageFailedError,
    StageUsage,
)
from homeworking.settings import Settings

SPEC = Spec(description="Regal", width_mm=800, depth_mm=300, height_mm=1800)
SPECIES = {"spruce": "Fichte"}

# --- the fixed values ---------------------------------------------------------------------------


def test_the_budgets_are_60_seconds_for_medium_and_90_for_heavy() -> None:
    assert TIME_BUDGET_S == {"medium": 60, "heavy": 90}


@pytest.mark.parametrize(
    ("description", "category"),
    [
        ("Schuhregal im Flur", "medium"),
        ("Podest für Kinder, 2 m lang", "medium"),
        ("Vogelhaus für den Balkon", "medium"),
        ("Regal neben der Haustür", "medium"),
        ("Hausschuhe-Ablage", "medium"),
        ("Fachwerkhaus", "heavy"),
        ("Gartenhaus 3 x 4 m", "heavy"),
        ("Ein Haus", "heavy"),
        ("Carport für zwei Autos", "heavy"),
        ("Pergola an der Terrasse", "heavy"),
        ("Zaun um den Garten", "heavy"),
    ],
)
def test_the_category_follows_the_words_of_the_brief(description: str, category: str) -> None:
    assert classify(Spec(description=description)) == category


def test_a_large_dimension_makes_any_construction_heavy() -> None:
    assert classify(Spec(description="Regal", width_mm=HEAVY_FROM_MM - 1)) == "medium"
    assert classify(Spec(description="Regal", width_mm=HEAVY_FROM_MM)) == "heavy"
    assert time_budget_s(Spec(description="Regal", depth_mm=HEAVY_FROM_MM)) == 90


# --- the budget of a chat turn ------------------------------------------------------------------


def _planner(*, time_budget: bool = True) -> ChatPlanner:
    return ChatPlanner(None, None, uuid4(), None, time_budget=time_budget)  # type: ignore[arg-type]


def test_the_chat_keeps_a_reserve_for_its_closing_message() -> None:
    budget = _planner()._budget_s(SPEC)
    assert budget is not None
    assert 60 - CHAT_RESERVE_S - 1 < budget <= 60 - CHAT_RESERVE_S


def test_a_second_plan_of_the_same_turn_gets_only_what_is_left() -> None:
    planner = _planner()
    planner._started -= 20  # the first plan took 20 s
    budget = planner._budget_s(SPEC)
    assert budget is not None
    assert budget < 60 - CHAT_RESERVE_S - 19


def test_the_budget_can_be_switched_off_for_tools() -> None:
    assert _planner(time_budget=False)._budget_s(SPEC) is None


# --- the pipeline respects the deadline ---------------------------------------------------------


def _slow(model: FunctionModel, seconds: float) -> FunctionModel:
    """The offline stage model, answering only after ``seconds``."""
    inner = model.function

    async def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        await asyncio.sleep(seconds)
        return inner(messages, info)  # type: ignore[return-value, misc]

    return FunctionModel(respond, model_name=model.model_name)


def _pipeline(**models: FunctionModel) -> Pipeline:
    return Pipeline(Settings(llm_mode="test"), None, SPECIES, **models)  # type: ignore[arg-type]


async def test_enough_time_changes_nothing() -> None:
    result = await _pipeline().design(SPEC, budget_s=30)
    assert result.design.parts
    assert result.explanation


async def test_a_slow_module_stage_ends_at_the_deadline_and_not_with_the_model() -> None:
    pipeline = _pipeline(module_model=_slow(offline.module_model(), 5))
    started = time.perf_counter()
    with pytest.raises(StageFailedError) as failed:
        await pipeline.design(SPEC, budget_s=0.5)
    assert time.perf_counter() - started < 2
    assert isinstance(failed.value.cause, DeadlineExceededError)
    assert failed.value.usage.stage == "modules"  # the failed stage is still reported (and stored)


async def test_a_slow_skeleton_stage_ends_at_the_deadline_too() -> None:
    pipeline = _pipeline(skeleton_model=_slow(offline.skeleton_model(), 5))
    started = time.perf_counter()
    with pytest.raises(StageFailedError) as failed:
        await pipeline.design(SPEC, budget_s=0.5)
    assert time.perf_counter() - started < 2
    assert isinstance(failed.value.cause, DeadlineExceededError)
    assert failed.value.usage.stage == "skeleton"


async def test_every_failed_stage_reaches_the_recorder() -> None:
    seen: list[tuple[str, str | None]] = []

    async def record(usage: StageUsage, error: str | None) -> None:
        seen.append((usage.stage, error))

    pipeline = _pipeline(module_model=_slow(offline.module_model(), 5))
    with pytest.raises(StageFailedError):
        await pipeline.design(SPEC, on_stage=record, budget_s=0.5)
    assert [stage for stage, _ in seen] == ["skeleton", "modules"]
    assert seen[1][1] is not None


async def test_the_documentation_falls_back_when_the_time_is_up() -> None:
    pipeline = _pipeline(docs_model=_slow(offline.docs_model(), 5))
    started = time.perf_counter()
    result = await pipeline.design(SPEC, budget_s=1.5)
    assert time.perf_counter() - started < 3
    assert result.explanation is None  # no texts, but the checked design is delivered
    assert result.design.parts
    assert result.design.steps  # the engine's plain step texts


async def test_repair_rounds_stop_when_another_round_would_not_fit() -> None:
    calls: list[int] = []
    bad_part = {
        "id": "left",
        "name": "Seite",
        "material": "no_such_material",
        "size": [18, 300, 1800],
        "at": [0, 0, 0],
    }

    async def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append(1)
        await asyncio.sleep(0.3)
        answer: dict[str, Any] = {"module": "body", "parts": [bad_part]}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, answer)])

    pipeline = _pipeline(module_model=FunctionModel(respond, model_name="always-wrong"))
    started = time.perf_counter()
    with pytest.raises((ModulesRejectedError, StageFailedError)):
        await pipeline.design(SPEC, budget_s=1.0)
    assert time.perf_counter() - started < 1.5
    assert 1 < len(calls) < 5  # repaired at least once, but not as often as without a deadline


async def test_without_a_budget_the_pipeline_is_not_limited() -> None:
    pipeline = _pipeline(module_model=_slow(offline.module_model(), 0.3))
    result = await pipeline.design(SPEC)
    assert result.design.parts


def test_the_deadline_error_is_a_timeout() -> None:
    assert issubclass(DeadlineExceededError, TimeoutError)
