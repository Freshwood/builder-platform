"""Designs through the pipeline with building blocks: no module model, whatever the model's speed.

The module model of these tests fails the test when it is called: a block module is written by the
engine, so a house, a shelf or a pergola must be finished without a single module request. This is
what makes the time budget independent of the model (docs/ai/ZEITBUDGET.md).
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from homeworking.calc_engine.pipeline.budget import TIME_BUDGET_S, classify
from homeworking.construction_model.pipeline import Spec
from homeworking.modules.pipeline import offline
from homeworking.modules.pipeline.stages import Pipeline
from homeworking.settings import Settings

SPECIES = {"larch": "Lärche", "spruce": "Fichte"}
SETTINGS = Settings(environment="test", llm_mode="test")


def _no_module_calls() -> FunctionModel:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise AssertionError("a block module must not ask the module model")

    return FunctionModel(respond, model_name="no-modules")


def _skeleton(modules: list[dict[str, Any]], **params: int) -> dict[str, Any]:
    sizes = {"width_mm": 4000, "depth_mm": 3000, "height_mm": 4000, **params}
    return {
        "object_type": "Objekt",
        "summary": "s",
        "params": [
            {"name": k, "label": k, "kind": "length", "default": v, "min": 1, "max": 100_000}
            for k, v in sizes.items()
        ],
        "modules": modules,
    }


def _scripted(*answers: dict[str, Any]) -> FunctionModel:
    queue = list(answers)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        data = queue.pop(0) if len(queue) > 1 else queue[0]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, data)])

    return FunctionModel(respond, model_name="scripted-skeleton")


def _module(block: dict[str, Any] | None) -> dict[str, Any]:
    box = ["width_mm", "depth_mm", "height_mm"]
    brief: dict[str, Any] = {
        "id": "obj",
        "title": "Objekt",
        "role": "Objekt",
        "origin": [0, 0, 0],
        "size": box,
    }
    if block is not None:
        brief["block"] = block
    return brief


def _pipeline(skeleton: FunctionModel | None = None, adopt: bool | None = None) -> Pipeline:
    return Pipeline(
        SETTINGS,
        None,
        SPECIES,
        skeleton_model=skeleton,
        module_model=_no_module_calls(),
        adopt_blocks=adopt,
    )


async def test_the_offline_skeleton_builds_a_house_without_a_module_model() -> None:
    started = time.perf_counter()
    result = await _pipeline().design(
        Spec(description="Fachwerkhaus als Gartenhaus"), budget_s=TIME_BUDGET_S["heavy"]
    )
    assert time.perf_counter() - started < 10
    assert result.design.category == "building"
    assert [s.title for s in result.design.steps] == [
        "Fundament und Boden",
        "Wände aufstellen",
        "Dach",
    ]
    modules = next(s for s in result.stages if s.stage == "modules")
    assert modules.requests == 0  # nothing was asked of a model
    docs = next(s for s in result.stages if s.stage == "docs")
    assert docs.requests == 0  # explanation and steps are the block's own
    assert result.explanation is not None
    assert "Punktfundamenten" in result.explanation


@pytest.mark.parametrize(
    ("brief", "kind", "size"),
    [
        ("Schuhregal für den Flur", "carcass", (800, 300, 1800)),
        ("Ein Podest für die Kinder", "platform", (2000, 1000, 300)),
        ("Gartentisch für sechs Personen", "table", (1800, 900, 750)),
        ("Carport für zwei Autos", "post_frame", (5000, 3000, 2800)),
        ("Zaun um den Garten", "fence", (6000, 90, 1200)),
    ],
)
async def test_a_hand_made_single_module_becomes_a_block_and_needs_no_module_model(
    brief: str, kind: str, size: tuple[int, int, int]
) -> None:
    """The skeleton model forgot the block; the brief names the object, the engine adopts it."""
    sizes = dict(zip(("width_mm", "depth_mm", "height_mm"), size, strict=True))
    pipeline = _pipeline(_scripted(_skeleton([_module(None)], **sizes)), adopt=True)
    result = await pipeline.design(Spec(description=brief), budget_s=60)
    assert result.skeleton.modules[0].block is not None
    assert result.skeleton.modules[0].block.kind == kind
    assert next(s for s in result.stages if s.stage == "modules").requests == 0


async def test_without_adoption_the_models_own_module_stays() -> None:
    pipeline = Pipeline(
        SETTINGS,
        None,
        SPECIES,
        skeleton_model=_scripted(
            _skeleton([_module(None)], width_mm=800, depth_mm=300, height_mm=1800)
        ),
        module_model=offline.module_model(),
        adopt_blocks=False,
    )
    result = await pipeline.design(Spec(description="Schuhregal"), budget_s=60)
    assert result.skeleton.modules[0].block is None
    assert next(s for s in result.stages if s.stage == "modules").requests == 1


async def test_a_block_that_does_not_fit_is_revised_in_the_skeleton() -> None:
    """A door too close to the corner: the block says what to change, the skeleton model corrects it."""
    bad = {"kind": "house", "openings": [{"wall": "front", "kind": "door", "at": 100}]}
    good = {"kind": "house", "openings": [{"wall": "front", "kind": "door"}]}
    result = await _pipeline(
        _scripted(_skeleton([_module(bad)]), _skeleton([_module(good)]))
    ).design(Spec(description="Fachwerkhaus"), budget_s=TIME_BUDGET_S["heavy"])
    assert result.skeleton.modules[0].block is not None
    assert result.skeleton.modules[0].block.openings[0].at is None  # type: ignore[index]


async def test_a_height_the_model_picked_is_corrected_without_asking_again() -> None:
    low = _skeleton([_module({"kind": "house"})], height_mm=2500)
    result = await _pipeline(_scripted(low)).design(
        Spec(description="Fachwerkhaus"), budget_s=TIME_BUDGET_S["heavy"]
    )
    height = next(p for p in result.skeleton.params if p.name == "height_mm")
    assert height.default >= 3500
    assert next(s for s in result.stages if s.stage == "skeleton").requests == 1


async def test_customer_dimensions_move_the_block() -> None:
    spec = Spec(description="Fachwerkhaus", width_mm=5000, depth_mm=4000, height_mm=4500)
    result = await _pipeline().design(spec, budget_s=TIME_BUDGET_S["heavy"])
    values = {p.name: p.default for p in result.design.params}
    assert (values["width_mm"], values["depth_mm"], values["height_mm"]) == (5000, 4000, 4500)


def test_every_building_brief_is_heavy_and_gets_the_heavy_budget() -> None:
    for text in ("Carport", "Fachwerkhaus", "Pergola", "Zaun um den Garten"):
        assert classify(Spec(description=text)) == "heavy"


async def test_a_table_the_model_planned_in_several_modules_becomes_one_block() -> None:
    """The model split a table into frame and top; the brief names a table, the engine builds it."""
    frame = {**_module(None), "id": "gestell", "title": "Gestell"}
    top = {**_module(None), "id": "platte", "title": "Platte"}
    sizes = {"width_mm": 1800, "depth_mm": 900, "height_mm": 750}
    pipeline = _pipeline(_scripted(_skeleton([frame, top], **sizes)), adopt=True)
    result = await pipeline.design(Spec(description="Gartentisch für sechs Personen"), budget_s=60)
    assert [m.block.kind for m in result.skeleton.modules if m.block] == ["table"]
    assert len(result.skeleton.modules) == 1
    assert next(s for s in result.stages if s.stage == "modules").requests == 0


async def test_a_special_wish_keeps_the_models_own_modules() -> None:
    wish = Spec(description="Tisch mit Schublade und runder Platte")
    sizes = {"width_mm": 1800, "depth_mm": 900, "height_mm": 750}
    pipeline = Pipeline(
        SETTINGS,
        None,
        SPECIES,
        skeleton_model=_scripted(_skeleton([_module(None)], **sizes)),
        module_model=offline.module_model(),
        adopt_blocks=True,
    )
    result = await pipeline.design(wish, budget_s=60)
    assert result.skeleton.modules[0].block is None


async def test_an_extra_module_that_fails_is_dropped_and_the_block_is_delivered() -> None:
    """Seen live: a carport block plus a hand-planned back wall that ran out of tokens."""
    wall = {**_module(None), "id": "rueckwand", "title": "Rückwand"}
    sizes = {"width_mm": 5000, "depth_mm": 3000, "height_mm": 2800}
    broken = FunctionModel(
        lambda messages, info: (_ for _ in ()).throw(RuntimeError("provider failed")),
        model_name="broken-modules",
    )
    pipeline = Pipeline(
        SETTINGS,
        None,
        SPECIES,
        skeleton_model=_scripted(
            _skeleton([_module({"kind": "post_frame", "roof": "shed"}), wall], **sizes)
        ),
        module_model=broken,
        adopt_blocks=False,
    )
    result = await pipeline.design(Spec(description="Carport für zwei Autos"), budget_s=60)
    assert [m.id for m in result.skeleton.modules] == ["obj"]
    assert result.explanation is not None
    assert "Rückwand" in result.explanation  # the customer is told what is missing
