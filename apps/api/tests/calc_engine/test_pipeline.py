"""Staged pipeline (ADR-0010): gaps in the brief and merging modules into one design."""

from datetime import UTC, datetime
from typing import Any

import pytest

from design_fixtures import fixture_design
from homeworking.calc_engine.engine import default_engine
from homeworking.calc_engine.pipeline.gaps import apply_updates, is_ready, open_questions
from homeworking.calc_engine.pipeline.materials import digest
from homeworking.calc_engine.pipeline.merge import (
    SKELETON,
    attribute,
    check,
    localize,
    merge,
    shift,
)
from homeworking.calc_engine.pipeline.skeleton import (
    check_skeleton,
    default_params,
    finish_item,
    module_box,
    normalize,
)
from homeworking.construction_model.assembly import AssemblyDesign
from homeworking.construction_model.model import ProjectInputs
from homeworking.construction_model.pipeline import (
    ModuleBrief,
    ModuleDesign,
    Skeleton,
    Spec,
    SpecUpdates,
)

engine = default_engine(clock=lambda: datetime(2026, 10, 2, 12, 0, tzinfo=UTC))
ZERO = (0, 0, 0)
BIG = ("width_mm", "depth_mm", "height_mm")


def shelf_modules(
    shelf: AssemblyDesign, *, origin: tuple[Any, Any, Any] = ZERO
) -> tuple[Skeleton, list[ModuleDesign]]:
    """The shelf fixture cut into a body (sides, back) and the shelf boards."""
    body = [p for p in shelf.parts if p.id != "shelf"]
    boards = [p for p in shelf.parts if p.id == "shelf"]
    skeleton = Skeleton(
        object_type=shelf.object_type,
        summary=shelf.summary,
        use=shelf.use,
        support=shelf.support,
        finish=shelf.finish,
        params=shelf.params,
        variants=shelf.variants,
        modules=[
            ModuleBrief(
                id="body", title="Korpus", role="Seiten und Rückwand", origin=origin, size=BIG
            ),
            ModuleBrief(id="boards", title="Böden", role="Fachböden", origin=origin, size=BIG),
        ],
    )
    return skeleton, [
        ModuleDesign(module="body", parts=body),
        ModuleDesign(module="boards", parts=boards),
    ]


def build(design: AssemblyDesign) -> Any:
    return engine.build(ProjectInputs(title="t", params={}, design=design))


def test_merged_modules_build_the_same_construction() -> None:
    shelf = fixture_design("shelf")
    merged = merge(*shelf_modules(shelf))
    assert merged.ok
    assert merged.design is not None
    assert not check(engine, merged).errors
    original, joined = build(shelf), build(merged.design)
    assert sorted((c.part, c.count) for c in joined.cut_list) == sorted(
        (c.part, c.count) for c in original.cut_list
    )
    assert (
        joined.key_figures["Außenmaße (B × T × H)"] == original.key_figures["Außenmaße (B × T × H)"]
    )


def test_module_origin_moves_parts_but_not_the_object_size() -> None:
    shelf = fixture_design("shelf")
    merged = merge(*shelf_modules(shelf, origin=(500, 200, 0)))
    assert merged.design is not None
    moved = next(p for p in merged.design.parts if p.id == "body_side_right")
    assert moved.at == ("(500) + (width_mm - 18)", 200, 0)
    assert (
        build(merged.design).key_figures["Außenmaße (B × T × H)"]
        == build(shelf).key_figures["Außenmaße (B × T × H)"]
    )


def test_module_condition_applies_to_all_its_parts() -> None:
    shelf = fixture_design("shelf")
    skeleton, modules = shelf_modules(shelf)
    skeleton = skeleton.model_copy(
        update={
            "modules": [
                skeleton.modules[0],
                skeleton.modules[1].model_copy(update={"when": "shelves > 2"}),
            ]
        }
    )
    merged = merge(skeleton, modules)
    assert merged.design is not None
    assert next(p for p in merged.design.parts if p.id == "boards_shelf").when == "shelves > 2"


def test_missing_unknown_and_duplicate_modules_are_reported_per_module() -> None:
    skeleton, modules = shelf_modules(fixture_design("shelf"))
    only_body = merge(skeleton, modules[:1])
    assert only_body.design is None
    assert set(only_body.errors) == {"boards"}
    stranger = ModuleDesign(module="roof", parts=modules[0].parts)
    assert "roof" in merge(skeleton, [*modules, stranger]).errors
    assert "body" in merge(skeleton, [*modules, modules[0]]).errors


def test_engine_error_goes_back_to_the_module_that_owns_the_part() -> None:
    skeleton, modules = shelf_modules(fixture_design("shelf"))
    bad = modules[1].parts[0].model_copy(update={"material": "no_such_material"})
    merged = merge(skeleton, [modules[0], ModuleDesign(module="boards", parts=[bad])])
    checked = check(engine, merged)
    assert not checked.ok
    assert set(checked.errors) == {"boards"}


def test_attribution_without_a_part_name_falls_back_to_the_skeleton() -> None:
    assert attribute(["Der Entwurf ist zu groß"], {"body_side": "body"}) == {
        SKELETON: ["Der Entwurf ist zu groß"]
    }
    assert attribute(
        ["Bauteil 'body_side': zu lang"], {"body_side": "body", "body_si": "body"}
    ) == {"body": ["Bauteil 'body_side': zu lang"]}


@pytest.mark.parametrize(
    ("origin", "value", "expected"),
    [(0, "a", "a"), ("a", 0, "a"), (10, 5, 15), (10, "w", "(10) + (w)"), ("o", "w", "(o) + (w)")],
)
def test_shift(origin: Any, value: Any, expected: Any) -> None:
    assert shift(origin, value) == expected


def test_nothing_known_asks_for_the_size_first_but_never_blocks() -> None:
    questions = open_questions(Spec(description="Ein Regal"))
    assert questions[0].field == "size"
    assert questions[0].blocking
    assert len(questions) == 3
    assert is_ready(Spec(description="Ein Regal"))
    assert not is_ready(Spec(description=" "))


def test_answered_fields_are_not_asked_again() -> None:
    spec = Spec(
        description="Regal",
        width_mm=800,
        depth_mm=300,
        height_mm=1800,
        use="indoor",
        support="floor",
        wood="spruce",
        finish="oil",
        experience="advanced",
    )
    assert open_questions(spec) == []
    assert is_ready(spec)


def test_finish_and_experience_are_asked_only_when_thorough() -> None:
    spec = Spec(
        description="Regal",
        width_mm=800,
        depth_mm=300,
        height_mm=1800,
        use="indoor",
        support="floor",
        wood="spruce",
    )
    assert open_questions(spec) == []
    assert [q.field for q in open_questions(spec, thorough=True)] == ["finish", "experience"]


def test_partial_size_is_a_soft_question() -> None:
    spec = Spec(description="Regal", width_mm=800, height_mm=1800)
    first = open_questions(spec)[0]
    assert first.field == "size"
    assert not first.blocking
    assert "Tiefe" in first.text
    assert is_ready(spec)


# --- stage 1 and 2 rules -------------------------------------------------------------------


def test_updates_fill_only_open_fields() -> None:
    spec = Spec(description="Regal", width_mm=800, use="indoor")
    filled = apply_updates(
        spec, SpecUpdates(width_mm=999, height_mm=1800, use="outdoor", size_mode="max")
    )
    assert filled.width_mm == 800  # the customer's own value wins
    assert filled.use == "indoor"
    assert filled.height_mm == 1800
    assert filled.size_mode == "max"


def test_explicit_size_mode_is_kept() -> None:
    spec = Spec(description="Regal", size_mode="exact")
    assert apply_updates(spec, SpecUpdates(size_mode="max")).size_mode == "exact"


def _skeleton() -> Skeleton:
    shelf = fixture_design("shelf")
    return shelf_modules(shelf)[0]


def test_normalize_applies_the_customers_facts() -> None:
    spec = Spec(
        description="Regal",
        width_mm=1000,
        use="outdoor",
        support="wall",
        finish="oil",
        size_mode="max",
    )
    skeleton = normalize(_skeleton(), spec)
    width = next(p for p in skeleton.params if p.name == "width_mm")
    assert (width.default, width.max) == (1000, 1000)
    assert skeleton.use == "outdoor"
    assert skeleton.support == "wall"
    assert skeleton.finish == "finish_oil_outdoor_750"


def test_normalize_widens_the_bounds_for_an_approximate_size() -> None:
    skeleton = normalize(_skeleton(), Spec(description="Regal", width_mm=2500))
    width = next(p for p in skeleton.params if p.name == "width_mm")
    assert (width.default, width.max) == (2500, 2500)


def test_a_valid_skeleton_has_no_problems() -> None:
    spec = Spec(description="Regal", width_mm=800, height_mm=1800)
    assert check_skeleton(normalize(_skeleton(), spec), spec) == []


def test_skeleton_problems_are_named_for_the_model() -> None:
    skeleton = _skeleton()
    broken = skeleton.model_copy(
        update={
            "modules": [
                skeleton.modules[0].model_copy(update={"size": ("nope", 10, 0)}),
                skeleton.modules[0],
            ],
            "params": [p for p in skeleton.params if p.name != "height_mm"],
        }
    )
    problems = check_skeleton(broken, Spec(description="x", height_mm=1800))
    text = " | ".join(problems)
    assert "height_mm' für die Maße" in text
    assert "doppelt" in text
    assert "size x" in text
    assert "größer als 0" in text


@pytest.mark.parametrize(
    ("finish", "use", "item"),
    [("oil", "indoor", "finish_hardwax_750"), ("natural", "indoor", None), (None, "outdoor", None)],
)
def test_finish_item(finish: str | None, use: str, item: str | None) -> None:
    assert finish_item(finish, use) == item


def test_engine_messages_are_rewritten_to_the_modules_own_ids() -> None:
    owners = {"boards_shelf": "boards", "body_shelf": "body"}
    text = "Bauteil 'boards_shelf' ragt in body_shelf; boards_shelf2 bleibt"
    assert localize([text], "boards", owners) == [
        "Bauteil 'shelf' ragt in body_shelf; boards_shelf2 bleibt"
    ]
    assert localize([text], "other", owners) == [text]


def test_module_box_is_evaluated_at_the_default_parameters() -> None:
    skeleton = _skeleton()
    brief = skeleton.modules[0].model_copy(
        update={"origin": (0, 0, "height_mm - 18"), "size": ("width_mm", 300, 18)}
    )
    params = default_params(skeleton)
    origin, size = module_box(brief, params)
    assert origin == (0, 0, int(params["height_mm"]) - 18)  # type: ignore[call-overload]
    assert size == (int(params["width_mm"]), 300, 18)  # type: ignore[call-overload]


def test_material_digest_lists_catalog_ids_without_prices() -> None:
    text = digest(engine.catalog)
    assert "plywood_birch_18" in text
    assert "lumber_<holzart>_<stärke>x<breite>" in text
    assert "larch" in text
    assert "€" not in text
    assert "finish_oil_outdoor_750" not in text  # the skeleton picks the finish
    assert len(text) < 2_000
