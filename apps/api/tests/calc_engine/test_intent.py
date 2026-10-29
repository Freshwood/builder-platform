"""Intent check: a built construction must match what the user asked for.

Every rule of ``homeworking.calc_engine.assembly.intent`` has a passing and a failing case, built through the
real engine from the fixture designs and from the podium of docs/problems/bug.md. No LLM, no
network. The podium is the motivating case: it passes every corpus invariant and still can be
too big or have no walkable top.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from pydantic import ValidationError

from design_fixtures import fixture_design, fixture_designs
from homeworking.calc_engine.assembly.intent import (
    FEATURE_PARAMS,
    Expectation,
    Violation,
    bounding_box,
    evaluate,
    solid_bounds,
    view_consistency,
)
from homeworking.calc_engine.engine import default_engine
from homeworking.construction_model.assembly import AssemblyDesign
from homeworking.construction_model.drawing import Dimension
from homeworking.construction_model.model import ConstructionResult, ProjectInputs

ENGINE = default_engine()

#: The podium expectation from the bug report: at most 2 x 1 m, indoor, boards or panel on top.
PODIUM_EXPECTATION: dict[str, Any] = {
    "envelope": {"max_length_mm": 2000, "max_width_mm": 1000},
    "use": "indoor",
    "support": "floor",
    "features": [{"walkable_top": {"min_coverage": 0.9}}, "choice_param:surface=boards|panel"],
}


def _corpus_podium() -> dict[str, Any]:
    from corpus_designs import PODIUM

    return copy.deepcopy(PODIUM)


def build(
    design: AssemblyDesign | dict[str, Any], **params: Any
) -> tuple[ProjectInputs, ConstructionResult]:
    if isinstance(design, dict):
        design = AssemblyDesign.model_validate(design)
    inputs = ProjectInputs(title="t", params=params, design=design)
    return inputs, ENGINE.build(inputs)


def fixture_build(key: str, **params: Any) -> tuple[ProjectInputs, ConstructionResult]:
    return build(fixture_design(key), **params)


def check(
    built: tuple[ProjectInputs, ConstructionResult], expectation: dict[str, Any]
) -> list[Violation]:
    inputs, result = built
    return evaluate(inputs, result, Expectation.model_validate(expectation), ENGINE)


def rules(violations: list[Violation]) -> list[str]:
    return [v.rule for v in violations]


# --------------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------------


def test_expectation_loads_from_json_and_keeps_every_form_of_a_feature() -> None:
    data = json.loads(json.dumps(PODIUM_EXPECTATION))
    expectation = Expectation.model_validate(data)
    assert [f.name for f in expectation.features] == ["walkable_top", "choice_param"]
    assert expectation.features[0].params == {"min_coverage": 0.9}
    assert expectation.features[1].params == {"name": "surface", "values": ["boards", "panel"]}
    # Dumped data loads again, so a case file can be written by a tool.
    assert Expectation.model_validate_json(expectation.model_dump_json()) == expectation


@pytest.mark.parametrize(
    "feature",
    [
        "walkable_top",
        {"walkable_top": None},
        {"walkable_top": True},
        {"walkable_top": {}},
        {"walkable_top": {"min_coverage": 0.8, "max_height_mm": 500}},
        {"choice_param": {"name": "wood", "values": ["douglas", "larch"]}},
        "choice_param:wood=douglas|larch",
        {"hinged_doors": {"wings": 2, "min_hinges": 3}},
        "standing_stable",
        {"levels": {"min": 3}},
        {"contoured": {"min": 2}},
    ],
)
def test_every_feature_form_loads(feature: Any) -> None:
    assert Expectation.model_validate({"features": [feature]}).features


def test_the_vocabulary_is_the_documented_one() -> None:
    assert set(FEATURE_PARAMS) == {
        "walkable_top",
        "choice_param",
        "hinged_doors",
        "standing_stable",
        "levels",
        "contoured",
    }


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"features": ["walkabel_top"]}, "Unbekanntes Merkmal 'walkabel_top'"),
        ({"features": [{"flying": {}}]}, "Unbekanntes Merkmal 'flying'"),
        ({"features": [{"walkable_top": {"coverage": 0.9}}]}, "coverage"),
        ({"features": [{"walkable_top": {"min_coverage": 1.5}}]}, "min_coverage"),
        ({"features": ["walkable_top:0.9"]}, "keine Kurzform"),
        ({"features": ["choice_param:surface"]}, "choice_param:<name>"),
        ({"features": ["choice_param:surface="]}, "choice_param:<name>"),
        ({"features": [{"choice_param": {"name": "surface"}}]}, "values"),
        ({"features": [{"walkable_top": {}, "levels": {"min": 1}}]}, "genau ein Name"),
        ({"features": [42]}, "Text oder"),
        ({"features": "walkable_top"}, "Liste"),
        ({"envelope": {"max_len_mm": 2000}}, "max_len_mm"),
        ({"use": "garage"}, "use"),
        ({"support": "ceiling"}, "support"),
        ({"colour": "red"}, "colour"),
    ],
)
def test_a_bad_expectation_fails_at_load_time_with_a_clear_message(
    data: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        Expectation.model_validate(data)


def test_an_empty_expectation_is_always_met() -> None:
    assert check(fixture_build("shelf"), {}) == []


# --------------------------------------------------------------------------------------------
# Envelope
# --------------------------------------------------------------------------------------------

# Workbench fixture: 1500 x 650 x 900 mm (length x width x height).


@pytest.mark.parametrize(
    ("field", "ok", "too_tight"),
    [
        ("max_length_mm", 1500, 1400),
        ("max_width_mm", 650, 600),
        ("max_height_mm", 900, 800),
        ("min_length_mm", 1500, 1600),
        ("min_width_mm", 650, 700),
        ("min_height_mm", 900, 1000),
    ],
)
def test_envelope_limits(field: str, ok: int, too_tight: int) -> None:
    built = fixture_build("workbench")
    assert check(built, {"envelope": {field: ok}}) == []
    found = check(built, {"envelope": {field: too_tight}})
    assert rules(found) == [f"envelope.{field.removesuffix('_mm')}"]
    assert f"{too_tight} mm" in found[0].detail


def test_envelope_length_is_the_longer_side_whatever_the_orientation() -> None:
    """Depth 900 is longer than width 850 here: 'length' is the longer side, not the x axis."""
    deep = fixture_build("workbench", width_mm=850, depth_mm=900)
    assert check(deep, {"envelope": {"max_length_mm": 900, "max_width_mm": 850}}) == []
    found = check(deep, {"envelope": {"max_length_mm": 880}})
    assert rules(found) == ["envelope.max_length"]
    assert "900 mm" in found[0].detail


def test_envelope_accepts_rounding_noise_but_not_a_real_overrun() -> None:
    built = fixture_build("workbench", width_mm=1500)
    assert check(built, {"envelope": {"max_length_mm": 1499.6}}) == []
    assert check(built, {"envelope": {"max_length_mm": 1499}}) != []


def test_envelope_counts_rotated_parts() -> None:
    """A plate turned by 45 degrees reaches further than its unrotated box."""
    design = {
        "object_type": "Drehplatte",
        "summary": "Platte, um 45 Grad gedreht, auf Grundplatte",
        "params": [],
        "parts": [
            {
                "id": "base",
                "name": "Grundplatte",
                "material": "plywood_birch_18",
                "size": [1000, 500, 18],
                "at": [0, 0, 0],
            },
            {
                "id": "turned",
                "name": "Drehplatte",
                "material": "plywood_birch_18",
                "size": [500, 500, 18],
                "at": [500, 100, 18],
                "rotate": {"axis": "z", "deg": 45},
            },
        ],
    }
    built = build(design)
    box = bounding_box(built[1].solids)
    assert box is not None
    # Unrotated, the plate ends at y = 600; turned, its far corner is at 100 + 500 * sqrt(2).
    assert box[1][1] == pytest.approx(100 + 500 * 2**0.5, abs=1)
    assert check(built, {"envelope": {"max_width_mm": 700}}) != []
    assert view_consistency(built[1]) == []


def test_envelope_without_solids_cannot_be_checked() -> None:
    inputs, result = fixture_build("shelf")
    empty = result.model_copy(update={"solids": []})
    found = evaluate(inputs, empty, Expectation.model_validate({"envelope": {"max_length_mm": 1}}))
    assert rules(found) == ["envelope"]


# --------------------------------------------------------------------------------------------
# use, support, materials, parts
# --------------------------------------------------------------------------------------------


def test_use_and_support() -> None:
    shutter = fixture_build("window_shutter")  # outdoor, wall
    assert check(shutter, {"use": "outdoor", "support": "wall"}) == []
    found = check(shutter, {"use": "indoor", "support": "floor"})
    assert rules(found) == ["use", "support"]
    assert "'outdoor'" in found[0].detail
    assert "'wall'" in found[1].detail


def test_materials_any_wants_a_part_of_that_material() -> None:
    larch = fixture_build("garden_bench", wood="larch")
    douglas = fixture_build("garden_bench", wood="douglas")
    assert check(larch, {"materials_any": ["larch"]}) == []
    assert check(douglas, {"materials_any": ["larch", "oak"]}) != []
    assert check(douglas, {"materials_any": ["larch", "douglas"]}) == []
    found = check(douglas, {"materials_any": ["larch"]})
    assert rules(found) == ["materials_any"]
    assert "larch" in found[0].detail
    assert "board_douglas_28x145" in found[0].detail


def test_materials_none_excludes_a_material_such_as_squared_timber() -> None:
    """'Boards, not squared timber': catalog ids of squared timber start with 'square_'."""
    assert check(fixture_build("shelf"), {"materials_none": ["square_"]}) == []
    found = check(fixture_build("workbench"), {"materials_none": ["square_"]})
    assert rules(found) == ["materials_none"]
    assert "square_spruce_70x70" in found[0].detail


def test_parts_count_limits() -> None:
    built = fixture_build("shelf")  # 8 components
    assert len(built[1].components) == 8
    assert check(built, {"parts": {"min": 8, "max": 8}}) == []
    assert rules(check(built, {"parts": {"min": 9}})) == ["parts.min"]
    assert rules(check(built, {"parts": {"max": 7}})) == ["parts.max"]


# --------------------------------------------------------------------------------------------
# Features
# --------------------------------------------------------------------------------------------


def test_walkable_top_passes_for_a_full_surface() -> None:
    assert check(fixture_build("workbench"), {"features": ["walkable_top"]}) == []
    assert check(build(_corpus_podium(), surface="panel"), {"features": ["walkable_top"]}) == []
    assert check(build(_corpus_podium(), surface="boards"), {"features": ["walkable_top"]}) == []


def test_walkable_top_fails_when_a_back_wall_stands_above_the_surface() -> None:
    """The cloud shelf's base plate covers its footprint, but the cloud rises above it."""
    found = check(fixture_build("cloud_shelf"), {"features": ["walkable_top"]})
    assert rules(found) == ["feature.walkable_top"]
    assert "oberste" in found[0].detail


def test_walkable_top_fails_when_no_level_covers_enough() -> None:
    cloud = fixture_build("cloud_shelf")  # each shelf covers about 53 % of the footprint
    found = check(cloud, {"features": [{"walkable_top": {"min_height_mm": 100}}]})
    assert rules(found) == ["feature.walkable_top"]
    assert "Grundfläche" in found[0].detail
    assert "90 %" in found[0].detail


def test_walkable_top_coverage_parameter() -> None:
    """Eight 100 mm boards on a 125 mm pitch (the corpus pitch) cover 80 % of the podium."""
    podium = _corpus_podium()
    boards = next(p for p in podium["parts"] if p["id"] == "top_boards")
    boards["material"] = "lumber_spruce_18x100"
    boards["size"] = ["length_mm", 100, 18]
    # A batten between the frame rails keeps the gapped boards connected to the frame.
    podium["parts"].append(
        {
            "id": "batten",
            "name": "Querleiste",
            "material": "frame_spruce_44x44",
            "size": [44, "deck_boards * 125 - 88", 44],
            "at": ["length_mm / 2", 44, "height_mm - 62"],
        }
    )
    gapped = build(podium)
    assert check(gapped, {"features": [{"walkable_top": {"min_coverage": 0.75}}]}) == []
    found = check(gapped, {"features": ["walkable_top"]})
    assert rules(found) == ["feature.walkable_top"]
    assert "80 %" in found[0].detail


def test_walkable_top_height_range() -> None:
    workbench = fixture_build("workbench")  # top at 900, lower shelf top at 237
    in_range = {"walkable_top": {"min_height_mm": 850, "max_height_mm": 950}}
    assert check(workbench, {"features": [in_range]}) == []
    too_high = {"walkable_top": {"min_height_mm": 1000}}
    found = check(workbench, {"features": [too_high]})
    assert rules(found) == ["feature.walkable_top"]
    assert "Höhenbereich" in found[0].detail


def test_walkable_top_must_be_the_top_unless_allowed_otherwise() -> None:
    """A bench seat is covered, but the backrest stands above it."""
    bench = fixture_build("garden_bench")
    seat = {"min_coverage": 0.8, "max_height_mm": 460}
    found = check(bench, {"features": [{"walkable_top": seat}]})
    assert rules(found) == ["feature.walkable_top"]
    assert "oberste" in found[0].detail
    assert check(bench, {"features": [{"walkable_top": seat | {"allow_above": True}}]}) == []


def test_choice_param_passes_when_every_option_builds_and_fits() -> None:
    built = build(_corpus_podium())
    assert check(built, PODIUM_EXPECTATION) == []
    assert (
        check(fixture_build("garden_bench"), {"features": ["choice_param:wood=douglas|larch"]})
        == []
    )
    mapping = {"choice_param": {"name": "wood", "values": ["oak", "pine"]}}
    assert check(fixture_build("window_shutter"), {"features": [mapping]}) == []


@pytest.mark.parametrize(
    ("feature", "message"),
    [
        ("choice_param:finish=boards|panel", "keinen Auswahlparameter 'finish'"),
        ("choice_param:length_mm=boards|panel", "keinen Auswahlparameter 'length_mm'"),
        ("choice_param:surface=boards|steel", "steel nicht an"),
    ],
)
def test_choice_param_fails_for_a_missing_parameter_or_option(feature: str, message: str) -> None:
    found = check(build(_corpus_podium()), {"features": [feature]})
    assert rules(found) == ["feature.choice_param"]
    assert message in found[0].detail


def test_choice_param_fails_when_an_option_does_not_build() -> None:
    design = {
        "object_type": "Brett",
        "summary": "Brett",
        "params": [
            {
                "name": "wood",
                "label": "Holzart",
                "kind": "choice",
                "default": "douglas",
                "options": [
                    {"value": "douglas", "label": "Douglasie"},
                    {"value": "unobtainium", "label": "Unbekannt"},
                ],
            }
        ],
        "parts": [
            {
                "id": "board",
                "name": "Brett",
                "material": "lumber_{wood}_18x96",
                "size": [96, 18, 400],
                "at": [0, 0, 0],
            }
        ],
    }
    found = check(build(design), {"features": ["choice_param:wood=douglas|unobtainium"]})
    assert rules(found) == ["feature.choice_param"]
    assert "wood=unobtainium lässt sich nicht bauen" in found[0].detail


def _oversized_boards_podium() -> dict[str, Any]:
    """The original corpus defect: ceil(1000 / 146) = 7 boards of 146 mm are 1022 mm wide."""
    podium = _corpus_podium()
    boards = next(p for p in podium["parts"] if p["id"] == "top_boards")
    boards["material"] = "board_spruce_18x146"
    boards["size"] = ["length_mm", 146, 18]
    boards["at"] = [0, "i * 146", "height_mm - 18"]
    boards["repeat"] = {"count": "ceil(deck_boards * 125 / 146)"}
    return podium


def test_choice_param_rechecks_the_geometry_of_every_option() -> None:
    """The panel option is 1000 mm wide, the boards option 1022 mm: only that one is named."""
    wanted = {"envelope": {"max_width_mm": 1000}, "features": ["choice_param:surface=boards|panel"]}
    found = check(build(_oversized_boards_podium()), wanted)
    assert rules(found) == ["envelope.max_width"]
    assert "1022" in found[0].detail
    only_panel = check(build(_oversized_boards_podium(), surface="panel"), wanted)
    assert rules(only_panel) == ["envelope.max_width"]
    assert only_panel[0].detail.startswith("[surface=boards]")


def test_corpus_podium_is_exactly_as_wide_as_requested_for_every_width() -> None:
    """Deck boards are 125 mm wide: every valid width is whole boards, for both surfaces."""
    for boards in range(5, 11):
        for surface in ("boards", "panel"):
            box = bounding_box(
                build(_corpus_podium(), deck_boards=boards, surface=surface)[1].solids
            )
            assert box is not None
            assert box[1][1] - box[0][1] == boards * 125


def test_hinged_doors() -> None:
    shutter = fixture_build("window_shutter")  # two wings, four hinges
    assert check(shutter, {"features": ["hinged_doors"]}) == []
    assert check(shutter, {"features": [{"hinged_doors": {"wings": 2, "min_hinges": 2}}]}) == []
    one_wing = fixture_build("window_shutter", wings=1)
    assert check(one_wing, {"features": ["hinged_doors"]}) == []


def test_hinged_doors_fails_with_too_few_hinges() -> None:
    shutter = fixture_build("window_shutter")
    found = check(shutter, {"features": [{"hinged_doors": {"wings": 3}}]})
    assert rules(found) == ["feature.hinged_doors"]
    assert "4 Scharniere für 3 Flügel" in found[0].detail
    assert check(shutter, {"features": [{"hinged_doors": {"min_hinges": 3}}]}) != []
    found = check(fixture_build("workbench"), {"features": ["hinged_doors"]})
    assert "0 Scharniere" in found[0].detail


def test_standing_stable() -> None:
    assert check(fixture_build("workbench"), {"features": ["standing_stable"]}) == []
    assert check(fixture_build("garden_bench"), {"features": ["standing_stable"]}) == []
    assert check(build(_corpus_podium()), {"features": ["standing_stable"]}) == []
    # Tall and narrow, but anchored to the wall by the design's tip-over kit.
    tall = fixture_build("shelf", width_mm=400, depth_mm=200, height_mm=2000)
    assert check(tall, {"features": ["standing_stable"]}) == []


def test_standing_stable_fails_for_wall_mounted_objects() -> None:
    found = check(fixture_build("window_shutter"), {"features": ["standing_stable"]})
    assert rules(found) == ["feature.standing_stable"]
    assert "wandmontiert" in found[0].detail


def test_standing_stable_ratio_parameter() -> None:
    workbench = fixture_build("workbench")  # 900 high on 650 deep: ratio 1.4
    assert check(workbench, {"features": [{"standing_stable": {"max_height_ratio": 1.5}}]}) == []
    found = check(workbench, {"features": [{"standing_stable": {"max_height_ratio": 1.0}}]})
    assert rules(found) == ["feature.standing_stable"]
    assert "Wandbefestigung" in found[0].detail


def test_standing_stable_fails_when_the_weight_overhangs_the_feet() -> None:
    design = {
        "object_type": "Auslegertisch",
        "summary": "Tisch mit einseitigen Beinen",
        "params": [],
        "parts": [
            {
                "id": "leg",
                "name": "Bein",
                "material": "square_spruce_70x70",
                "size": [70, 70, 382],
                "at": [0, "i * 330", 0],
                "repeat": {"count": 2},
            },
            {
                "id": "top",
                "name": "Platte",
                "material": "plywood_birch_18",
                "size": [2000, 400, 18],
                "at": [0, 0, 382],
            },
        ],
    }
    found = check(build(design), {"features": ["standing_stable"]})
    assert rules(found) == ["feature.standing_stable"]
    assert "Schwerpunkt" in found[0].detail


def test_levels() -> None:
    shelf = fixture_build("shelf")  # five shelves
    assert check(shelf, {"features": [{"levels": {"min": 5}}]}) == []
    found = check(shelf, {"features": [{"levels": {"min": 6}}]})
    assert rules(found) == ["feature.levels"]
    assert "5 Ebenen" in found[0].detail
    assert check(fixture_build("workbench"), {"features": [{"levels": {"min": 2}}]}) == []


def test_contoured() -> None:
    assert check(fixture_build("cloud_shelf"), {"features": ["contoured"]}) == []
    found = check(fixture_build("workbench"), {"features": ["contoured"]})
    assert rules(found) == ["feature.contoured"]
    assert "0 Bauteile mit Kontur" in found[0].detail


# --------------------------------------------------------------------------------------------
# The podium from docs/problems/bug.md
# --------------------------------------------------------------------------------------------


def test_podium_that_fits_the_request_meets_the_intent() -> None:
    for surface in ("boards", "panel"):
        assert check(build(_corpus_podium(), surface=surface), PODIUM_EXPECTATION) == []


def test_a_podium_of_2400_mm_is_too_long_and_the_message_names_the_limit() -> None:
    found = check(build(_corpus_podium(), length_mm=2400), PODIUM_EXPECTATION)
    assert "envelope.max_length" in rules(found)
    message = next(v for v in found if v.rule == "envelope.max_length").detail
    assert "2400 mm" in message
    assert "2000 mm" in message
    assert "Länge" in message


def test_corpus_podium_meets_the_bug_report() -> None:
    assert check(build(_corpus_podium()), PODIUM_EXPECTATION) == []


def test_corpus_podium_with_a_panel_top_meets_the_bug_report() -> None:
    panel_only = {k: v for k, v in PODIUM_EXPECTATION.items() if k != "features"}
    panel_only["features"] = [{"walkable_top": {"min_coverage": 0.9}}]
    assert check(build(_corpus_podium(), surface="panel"), panel_only) == []


# --------------------------------------------------------------------------------------------
# view_consistency
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(fixture_designs()))
def test_views_of_every_fixture_design_are_consistent(key: str) -> None:
    assert view_consistency(fixture_build(key)[1]) == []


def test_views_of_the_podium_are_consistent() -> None:
    assert view_consistency(build(_corpus_podium())[1]) == []
    assert view_consistency(build(_corpus_podium(), surface="panel")[1]) == []


def test_solid_bounds_match_the_drawn_extent_of_a_meshed_part() -> None:
    result = fixture_build("cloud_shelf")[1]
    assert any(s.mesh is not None for s in result.solids)
    lo, hi = solid_bounds(next(s for s in result.solids if s.mesh is not None))
    assert hi[0] - lo[0] == pytest.approx(750, abs=1)
    assert view_consistency(result) == []


def _tamper(
    result: ConstructionResult, view: str, index: int, **changes: Any
) -> ConstructionResult:
    """A copy of the result in which the ``index``-th dimension of a view is changed."""
    drawings = []
    for drawing in result.drawings:
        if drawing.view == view:
            seen = -1
            primitives = []
            for primitive in drawing.primitives:
                if isinstance(primitive, Dimension):
                    seen += 1
                    if seen == index:
                        primitive = primitive.model_copy(update=changes)
                primitives.append(primitive)
            drawing = drawing.model_copy(update={"primitives": primitives})
        drawings.append(drawing)
    return result.model_copy(update={"drawings": drawings})


def test_view_consistency_catches_a_changed_overall_width() -> None:
    result = fixture_build("workbench")[1]
    assert view_consistency(result) == []
    tampered = _tamper(result, "front", 0, text="1400")
    found = view_consistency(tampered)
    assert {"view.dimension", "view.dimension_line", "view.cross"} <= set(rules(found))
    dimension = next(v for v in found if v.rule == "view.dimension")
    assert "'front'" in dimension.detail
    assert "1400" in dimension.detail
    assert "1500" in dimension.detail


def test_view_consistency_catches_views_that_disagree_with_each_other() -> None:
    result = fixture_build("workbench")[1]
    # Plan and front both lose 100 mm of width, so each equals the other but not the solids ...
    tampered = _tamper(_tamper(result, "front", 0, text="1400"), "plan", 0, text="1400")
    found = view_consistency(tampered)
    assert "view.dimension" in rules(found)
    # ... and a single wrong view is also reported against the others.
    cross = [
        v
        for v in view_consistency(_tamper(result, "side", 1, text="800"))
        if v.rule == "view.cross"
    ]
    assert cross
    assert "Höhe" in cross[0].detail


def test_view_consistency_catches_a_dimension_line_that_does_not_match_its_text() -> None:
    result = fixture_build("workbench")[1]
    tampered = _tamper(result, "plan", 1, y1=-10.0)
    found = view_consistency(tampered)
    assert rules(found) == ["view.dimension_line"]
    assert "'plan'" in found[0].detail


def test_view_consistency_catches_a_broken_level_chain() -> None:
    result = fixture_build("workbench")[1]
    tampered = _tamper(result, "front", 2, text="500")
    found = view_consistency(tampered)
    assert rules(found) == ["view.chain"]


def test_view_consistency_catches_a_text_that_is_not_a_number() -> None:
    result = fixture_build("workbench")[1]
    found = view_consistency(_tamper(result, "side", 0, text="ca. 650"))
    assert "view.dimensions" in rules(found)


def test_view_consistency_catches_a_description_with_the_wrong_size() -> None:
    result = fixture_build("workbench")[1]
    drawings = [
        d.model_copy(update={"description": d.description.replace("1500 ×", "1450 ×")})
        for d in result.drawings
    ]
    found = view_consistency(result.model_copy(update={"drawings": drawings}))
    assert set(rules(found)) == {"view.description"}


def test_view_consistency_catches_solids_that_changed_after_drawing() -> None:
    result = fixture_build("workbench")[1]
    solids = [
        s.model_copy(update={"size": (s.size[0] + 100, *s.size[1:])})
        if s.part_id == "top[0]"
        else s
        for s in result.solids
    ]
    found = view_consistency(result.model_copy(update={"solids": solids}))
    assert "view.dimension" in rules(found)
    assert any("1500" in v.detail for v in found)


def test_view_consistency_without_solids_says_so() -> None:
    result = fixture_build("shelf")[1].model_copy(update={"solids": []})
    assert rules(view_consistency(result)) == ["view.solids"]
