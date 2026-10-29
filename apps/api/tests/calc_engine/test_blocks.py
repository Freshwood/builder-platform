"""Building blocks: the engine writes the modules of houses, furniture, frames and fences.

Every block is built at its default dimensions and at every corner of the slider ranges the skeleton
gets (``prepare``), and the usual engine checks run over the merged design: no overlaps, every part
touches another, catalog sections and stock lengths hold.
"""

from __future__ import annotations

import itertools
import time
from typing import Any

import pytest

from homeworking.calc_engine.engine import DesignRejectedError, default_engine
from homeworking.calc_engine.pipeline.blocks import BlockError, block_steps, expand, prepare
from homeworking.calc_engine.pipeline.blocks.suggest import adopt, suggest
from homeworking.calc_engine.pipeline.merge import check, merge, module_steps
from homeworking.construction_model.assembly import DesignParam
from homeworking.construction_model.model import ProjectInputs
from homeworking.construction_model.pipeline import BlockSpec, ModuleBrief, Skeleton, Spec

engine = default_engine()
DIMS = ("width_mm", "depth_mm", "height_mm")


def skeleton_for(
    kind: str,
    size: tuple[int, int, int],
    *,
    use: str = "indoor",
    support: str = "floor",
    given: set[str] | None = None,
    **options: Any,
) -> Skeleton:
    params = [
        DesignParam(name=n, label=n, kind="length", default=v, min=1, max=100_000)
        for n, v in zip(DIMS, size, strict=True)
    ]
    brief = ModuleBrief(
        id="m",
        title="M",
        role="M",
        origin=(0, 0, 0),
        size=DIMS,  # type: ignore[arg-type]
        block=BlockSpec(kind=kind, **options),  # type: ignore[arg-type]
    )
    return prepare(
        Skeleton(
            object_type="X",
            summary="s",
            use=use,  # type: ignore[arg-type]
            support=support,  # type: ignore[arg-type]
            params=params,
            modules=[brief],
        ),
        given,
    )


CASES: list[tuple[str, tuple[int, int, int], dict[str, Any]]] = [
    ("house", (4000, 3000, 4000), {}),
    ("house", (3000, 3000, 3800), {"frame": "stud", "cover": "tiles"}),
    ("house", (5000, 4000, 3800), {"frame": "stud", "roof": "flat"}),
    ("house", (6000, 4000, 4800), {"braces": False}),
    ("house", (4500, 3500, 3600), {"openings": []}),
    (
        "house",
        (5000, 4000, 4200),
        {
            "openings": [
                {"wall": "front", "kind": "door"},
                {"wall": "front", "kind": "window_large"},
                {"wall": "left", "kind": "window"},
            ]
        },
    ),
    ("carcass", (800, 300, 1200), {}),
    ("carcass", (1200, 350, 1800), {"shelves": 4, "columns": 2, "doors": True}),
    ("carcass", (600, 200, 900), {"shelves": 2, "back": False}),
    ("carcass", (1500, 400, 2000), {"shelves": 5, "columns": 3}),
    ("platform", (2000, 1000, 300), {}),
    ("platform", (3000, 2000, 500), {}),
    ("table", (1400, 800, 750), {}),
    ("table", (1800, 900, 750), {"lower_shelf": True}),
    ("table", (1200, 350, 450), {}),
    ("post_frame", (5000, 3000, 2800), {"roof": "shed"}),
    ("post_frame", (6000, 3500, 3000), {"roof": "shed", "cover": "tiles"}),
    ("post_frame", (4000, 3000, 2600), {"roof": "flat"}),
    ("post_frame", (5500, 6000, 3000), {"roof": "shed"}),  # beams along y, rafters in KVH
    ("post_frame", (8000, 6500, 2800), {"roof": "flat"}),
    ("house", (9000, 7000, 5500), {}),  # rafters and ties in KVH
    ("fence", (6000, 90, 1200), {}),
    ("fence", (3000, 90, 1800), {}),
]


@pytest.mark.parametrize(("kind", "size", "options"), CASES)
def test_block_builds_at_every_corner_of_its_ranges(
    kind: str, size: tuple[int, int, int], options: dict[str, Any]
) -> None:
    use = "outdoor" if kind in {"house", "post_frame", "fence"} else "indoor"
    skeleton = skeleton_for(kind, size, use=use, **options)
    defaults = {p.name: p.default for p in skeleton.params}
    design = merge(skeleton, [expand(skeleton.modules[0], defaults, "larch")]).design
    assert design is not None
    ranges = {p.name: (p.min, p.default, p.max) for p in skeleton.params}
    surfaces = ["panel", "boards"] if kind == "platform" else [None]
    for width, depth, height in itertools.product(*(ranges[n] for n in DIMS)):
        for surface in surfaces:
            values: dict[str, Any] = {"width_mm": width, "depth_mm": depth, "height_mm": height}
            if surface:
                values["surface"] = surface
            try:
                engine.validate_design(design, values)
            except DesignRejectedError as exc:
                pytest.fail(f"{kind} {options} at {values}: {exc.errors[0]}")


@pytest.mark.parametrize("kind", ["house", "post_frame", "fence"])
def test_large_blocks_lift_the_size_limit(kind: str) -> None:
    assert skeleton_for(kind, (4000, 3000, 3600), roof="flat").category == "building"


def test_a_block_module_takes_the_dimension_parameters_as_its_box() -> None:
    skeleton = skeleton_for("table", (1400, 800, 750))
    assert skeleton.modules[0].size == DIMS


def test_house_ranges_follow_what_the_block_can_do() -> None:
    skeleton = skeleton_for("house", (12000, 8000, 6000), use="outdoor")
    depth = next(p for p in skeleton.params if p.name == "depth_mm")
    assert (depth.min, depth.max) == (6000, 9000)  # rafters stay below the 13 m of KVH


def test_a_house_builds_complete_documents_quickly() -> None:
    skeleton = skeleton_for("house", (4000, 3000, 4000), use="outdoor")
    defaults = {p.name: p.default for p in skeleton.params}
    started = time.perf_counter()
    merged = merge(skeleton, [expand(skeleton.modules[0], defaults, "larch")])
    assert check(engine, merged, defaults).ok
    assert merged.design is not None
    result = engine.build(ProjectInputs(title="t", params={}, design=merged.design))
    assert time.perf_counter() - started < 5
    assert len(result.bom) > 5
    assert result.solids
    assert any(line.item_id.startswith("door_wood") for line in result.bom)


def test_house_steps_follow_the_construction_order() -> None:
    skeleton = skeleton_for("house", (4000, 3000, 4000), use="outdoor")
    defaults = {p.name: p.default for p in skeleton.params}
    merged = merge(skeleton, [expand(skeleton.modules[0], defaults, "larch")])
    assert merged.design is not None
    steps = module_steps(skeleton, merged.design, merged.part_module)
    assert [s.title for s in steps] == ["Fundament und Boden", "Wände aufstellen", "Dach"]
    mounted = [p for s in steps for p in s.parts]
    assert sorted(mounted) == sorted(p.id for p in merged.design.parts)  # each part in one step


def test_block_steps_cover_every_kind() -> None:
    for kind, size, options in CASES:
        skeleton = skeleton_for(kind, size, **options)
        defaults = {p.name: p.default for p in skeleton.params}
        design = expand(skeleton.modules[0], defaults, "spruce")
        ids = [p.id for p in design.parts]
        grouped = [i for _, _, group in block_steps(kind, ids) for i in group]
        assert sorted(grouped) == sorted(ids), kind


@pytest.mark.parametrize(
    ("kind", "size", "options", "message"),
    [
        ("house", (4000, 4000, 3000), {}, "zu niedrig"),
        ("house", (1500, 3000, 4000), {}, "mindestens 2000"),
        ("house", (4000, 3000, 9000), {}, "zu groß"),
        ("house", (4000, 3000, 5000), {"roof": "flat"}, "Flachdach"),
        ("table", (150, 800, 750), {}, "mindestens"),
        ("platform", (2000, 1000, 50), {}, "mindestens 100"),
        ("post_frame", (9000, 8500, 3000), {"roof": "shed"}, "Spannweite höchstens"),
        ("fence", (500, 90, 1200), {}, "mindestens 1000"),
    ],
)
def test_a_block_that_does_not_fit_says_what_to_change(
    kind: str, size: tuple[int, int, int], options: dict[str, Any], message: str
) -> None:
    skeleton = skeleton_for(kind, size, use="outdoor", given=set(DIMS), **options)
    defaults = {p.name: p.default for p in skeleton.params}
    with pytest.raises(BlockError, match=message):
        expand(skeleton.modules[0], defaults, "larch")


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Ich möchte ein kleines Fachwerkhaus bauen", "house"),
        ("Gartenhaus für Geräte", "house"),
        ("Carport für zwei Autos", "post_frame"),
        ("Pergola über der Terrasse", "post_frame"),
        ("Zaun um den Garten", "fence"),
        ("Podest für die Kinder", "platform"),
        ("Esstisch für sechs Personen", "table"),
        ("Werkbank für die Garage", "table"),
        ("Schuhregal im Flur", "carcass"),
        ("Kleiderschrank", "carcass"),
        ("Wandregal für Gewürze", "carcass"),
    ],
)
def test_the_engine_recognises_what_a_block_builds(text: str, kind: str) -> None:
    block = suggest(text)
    assert block is not None
    assert block.kind == kind


@pytest.mark.parametrize(
    "text",
    ["Haustür reparieren", "Hausschuhe ablegen", "Hundehütte", "Vogelhaus", "Etwas Hübsches"],
)
def test_words_that_only_look_like_a_building_get_no_block(text: str) -> None:
    assert suggest(text) is None


def _plain(modules: int = 1, use: str = "outdoor") -> Skeleton:
    params = [
        DesignParam(name=n, label=n, kind="length", default=v, min=1, max=100_000)
        for n, v in zip(DIMS, (4000, 3000, 4000), strict=True)
    ]
    brief = [
        ModuleBrief(
            id=f"m{i}",
            title="M",
            role="M",
            origin=(0, 0, 0),
            size=DIMS,  # type: ignore[arg-type]
        )
        for i in range(modules)
    ]
    return Skeleton(
        object_type="X",
        summary="s",
        use=use,
        params=params,
        modules=brief,  # type: ignore[arg-type]
    )


def test_a_single_hand_made_module_becomes_the_block_the_brief_asks_for() -> None:
    adopted = adopt(_plain(), Spec(description="Fachwerkhaus im Garten"))
    assert adopted.modules[0].block is not None
    assert adopted.modules[0].block.kind == "house"


def test_several_hand_made_modules_become_one_block_module() -> None:
    adopted = adopt(_plain(2), Spec(description="Fachwerkhaus"))
    assert [m.id for m in adopted.modules] == ["bau"]
    assert adopted.modules[0].block is not None


def test_adoption_leaves_a_skeleton_that_chose_a_block_alone() -> None:
    chosen = skeleton_for("table", (1400, 800, 750))
    assert adopt(chosen, Spec(description="Fachwerkhaus")) == chosen


def test_adoption_needs_the_dimension_parameters() -> None:
    skeleton = _plain().model_copy(update={"params": _plain().params[:2]})
    assert adopt(skeleton, Spec(description="Fachwerkhaus")).modules[0].block is None


def test_adoption_skips_a_block_that_does_not_fit_the_dimensions() -> None:
    small = _plain().model_copy(
        update={
            "params": [
                DesignParam(name=n, label=n, kind="length", default=v, min=1, max=9999)
                for n, v in zip(DIMS, (1200, 1000, 900), strict=True)
            ]
        }
    )
    assert adopt(small, Spec(description="Spielhaus")).modules[0].block is None


# --- what the engine corrects itself ------------------------------------------------------------


def _skeleton(
    kind: str, size: tuple[int, int, int], given: set[str] | None = None, **options: Any
) -> Skeleton:
    params = [
        DesignParam(name=n, label=n, kind="length", default=v, min=v, max=v)
        for n, v in zip(DIMS, size, strict=True)
    ]
    brief = ModuleBrief(
        id="m",
        title="M",
        role="M",
        origin=(0, 0, 0),
        size=DIMS,  # type: ignore[arg-type]
        block=BlockSpec(kind=kind, **options),  # type: ignore[arg-type]
    )
    return prepare(
        Skeleton(object_type="X", summary="s", use="outdoor", params=params, modules=[brief]),
        given,
    )


def _default(skeleton: Skeleton, name: str) -> float:
    return float(next(p.default for p in skeleton.params if p.name == name))  # type: ignore[arg-type]


def test_a_height_the_model_chose_is_raised_until_the_roof_fits() -> None:
    skeleton = _skeleton("house", (4000, 3000, 2500))
    assert _default(skeleton, "height_mm") >= 3500
    defaults = {p.name: p.default for p in skeleton.params}
    expand(skeleton.modules[0], defaults, "larch")  # builds now


def test_a_height_the_customer_stated_is_left_alone() -> None:
    skeleton = _skeleton("house", (4000, 3000, 2500), given={"height_mm"})
    assert _default(skeleton, "height_mm") == 2500
    defaults = {p.name: p.default for p in skeleton.params}
    with pytest.raises(BlockError, match="zu niedrig"):  # not even a flat roof fits
        expand(skeleton.modules[0], defaults, "larch")


def test_a_stated_height_too_low_for_a_gable_roof_gives_a_flat_roof() -> None:
    skeleton = _skeleton("house", (4000, 3000, 3200), given={"height_mm"})
    block = skeleton.modules[0].block
    assert block is not None
    assert block.roof == "flat"
    defaults = {p.name: p.default for p in skeleton.params}
    expand(skeleton.modules[0], defaults, "larch")  # builds, and the height stays the customer's
    assert _default(skeleton, "height_mm") == 3200


def test_other_dimensions_are_lifted_to_what_the_block_builds() -> None:
    assert _default(_skeleton("post_frame", (3000, 3000, 2000)), "height_mm") >= 2700
    assert _default(_skeleton("house", (1500, 1500, 4000)), "width_mm") == 2400
    assert _default(_skeleton("post_frame", (9000, 9500, 3000), roof="shed"), "width_mm") == 8000


def test_roof_defaults_follow_the_kind() -> None:
    """The model leaves roof open, or takes gable for a carport: the block decides."""
    carport = _skeleton("post_frame", (6000, 5000, 2800), roof="gable")
    defaults = {p.name: p.default for p in carport.params}
    names = {p.id for p in expand(carport.modules[0], defaults, "larch").parts}
    assert "cover" in names  # a shed roof has a covering
    shed = _skeleton("house", (4000, 3000, 3000), roof="shed")  # a hut with a lean-to roof
    defaults = {p.name: p.default for p in shed.params}
    expand(shed.modules[0], defaults, "larch")


def test_modules_next_to_a_house_that_it_already_contains_are_dropped() -> None:
    base = skeleton_for("house", (4000, 3000, 4000), use="outdoor")
    extra = [
        ModuleBrief(
            id="fundament", title="Fundament", role="Betonplatte", origin=(0, 0, 0), size=DIMS
        ),  # type: ignore[arg-type]
        ModuleBrief(
            id="terrasse", title="Terrasse", role="Holzdeck davor", origin=(0, -2000, 0), size=DIMS
        ),  # type: ignore[arg-type]
    ]
    mixed = prepare(base.model_copy(update={"modules": [*base.modules, *extra]}))
    assert [m.id for m in mixed.modules] == ["m", "terrasse"]


def test_an_invented_finish_is_dropped() -> None:
    from homeworking.calc_engine.pipeline.skeleton import normalize

    skeleton = skeleton_for("table", (1400, 800, 750)).model_copy(update={"finish": "Holzöl außen"})
    assert normalize(skeleton, Spec(description="Tisch")).finish is None
    oiled = normalize(skeleton, Spec(description="Tisch", use="outdoor", finish="oil"))
    assert oiled.finish == "finish_oil_outdoor_750"


def test_a_wall_shelf_is_wall_mounted_even_if_nobody_said_so() -> None:
    from homeworking.calc_engine.pipeline.skeleton import normalize

    skeleton = skeleton_for("carcass", (600, 200, 500))
    assert normalize(skeleton, Spec(description="Wandregal für Gewürze")).support == "wall"
    assert normalize(skeleton, Spec(description="Schuhregal")).support == "floor"
    stated = Spec(description="Wandregal", support="floor")
    assert normalize(skeleton, stated).support == "floor"


def test_a_podium_offers_its_deck_as_panel_or_boards() -> None:
    skeleton = skeleton_for("platform", (2000, 1000, 300))
    surface = next(p for p in skeleton.params if p.name == "surface")
    assert [o.value for o in surface.options] == ["panel", "boards"]
    defaults = {p.name: p.default for p in skeleton.params}
    design = merge(skeleton, [expand(skeleton.modules[0], defaults, "spruce")]).design
    assert design is not None
    for choice, material in (("panel", "plywood_birch_24"), ("boards", "cladding_larch_24")):
        built = engine.build(ProjectInputs(title="t", params={"surface": choice}, design=design))
        assert any(line.item_id.startswith(material) for line in built.bom), choice


def test_a_foundation_module_next_to_a_carport_is_dropped() -> None:
    base = skeleton_for("post_frame", (6000, 5000, 3000), use="outdoor", roof="shed")
    extra = ModuleBrief(
        id="fundament",
        title="Fundamente",
        role="Punktfundamente",
        origin=(0, 0, -300),
        size=DIMS,  # type: ignore[arg-type]
    )
    mixed = prepare(base.model_copy(update={"modules": [*base.modules, extra]}))
    assert [m.id for m in mixed.modules] == ["m"]


def test_the_podium_meets_the_catwalk_wishes_with_either_surface() -> None:
    """The reported case: walkable top, 2 x 1 m, indoors, surface of boards or a panel."""
    from homeworking.calc_engine.assembly.intent import Expectation, evaluate

    skeleton = skeleton_for("platform", (2000, 1000, 400))
    defaults = {p.name: p.default for p in skeleton.params}
    design = merge(skeleton, [expand(skeleton.modules[0], defaults, "spruce")]).design
    assert design is not None
    expectation = Expectation.model_validate(
        {
            "envelope": {"max_length_mm": 2000, "max_width_mm": 1000},
            "use": "indoor",
            "support": "floor",
            "features": [
                {"walkable_top": {"min_coverage": 0.9}},
                "choice_param:surface=boards|panel",
            ],
        }
    )
    for choice in ("panel", "boards"):
        inputs = ProjectInputs(title="t", params={"surface": choice}, design=design)
        result = engine.build(inputs)
        assert evaluate(inputs, result, expectation, engine) == [], choice


def test_only_dimensions_the_text_contains_count_as_stated() -> None:
    from homeworking.calc_engine.pipeline.skeleton import stated

    spec = Spec(
        description="Ein Podest, 2 m lang und 100 cm breit",
        width_mm=2000,
        depth_mm=1000,
        height_mm=400,
    )
    assert stated(spec) == {"width_mm", "depth_mm"}  # the height is the chat model's assumption
    assert stated(
        Spec(description="Zaun, 8 Meter lang, 1,2 m hoch", width_mm=8000, height_mm=1200)
    ) == {
        "width_mm",
        "height_mm",
    }
    assert stated(Spec(description="Regal 1.250 mm hoch", height_mm=250)) == set()


def test_a_chat_models_assumed_height_is_corrected_but_a_stated_one_is_not() -> None:
    from homeworking.calc_engine.pipeline.skeleton import normalize

    plain = skeleton_for("house", (4000, 3000, 4000), use="outdoor", given=set(DIMS))
    assumed = Spec(description="Fachwerkhaus im Garten", height_mm=2500)
    fitted = normalize(plain, assumed)
    assert _default(fitted, "height_mm") >= 3500
    insisted = Spec(description="Fachwerkhaus, 2,5 m hoch", height_mm=2500)
    assert _default(normalize(plain, insisted), "height_mm") == 2500


def test_a_summary_that_is_too_long_is_cut_not_rejected() -> None:
    skeleton = skeleton_for("table", (1400, 800, 750))
    long = Skeleton(
        object_type="X", summary="x" * 400, params=skeleton.params, modules=skeleton.modules
    )
    assert len(long.summary) == 200


def test_a_block_the_model_hung_on_one_part_of_a_table_is_the_whole_table() -> None:
    """Seen live: modules top (28 mm tall) and frame, the table block on the top only."""
    top = ModuleBrief(
        id="platte",
        title="Platte",
        role="Platte",
        origin=(0, 0, 722),
        size=("width_mm", "depth_mm", 28),  # type: ignore[arg-type]
        block=BlockSpec(kind="table"),
    )
    frame = ModuleBrief(
        id="gestell",
        title="Gestell",
        role="Gestell",
        origin=(0, 0, 0),
        size=("width_mm", "depth_mm", "height_mm - 28"),  # type: ignore[arg-type]
    )
    params = [
        DesignParam(name=n, label=n, kind="length", default=v, min=1, max=100_000)
        for n, v in zip(DIMS, (1800, 870, 750), strict=True)
    ]
    skeleton = prepare(
        Skeleton(object_type="Tisch", summary="s", params=params, modules=[top, frame]),
        set(DIMS),
    )
    assert [m.id for m in skeleton.modules] == ["platte"]
    assert skeleton.modules[0].size == DIMS
    assert skeleton.modules[0].origin == (0, 0, 0)
    defaults = {p.name: p.default for p in skeleton.params}
    expand(skeleton.modules[0], defaults, "douglas")


def test_use_follows_the_words_of_the_brief() -> None:
    from homeworking.calc_engine.pipeline.blocks.suggest import infer_use

    assert infer_use("Gartentisch für sechs Personen") == "outdoor"
    assert infer_use("Carport für zwei Autos") == "outdoor"
    assert infer_use("Schuhregal im Flur") == "indoor"
    assert infer_use("Regal im Kinderzimmer, Motiv Gartenhaus") == "indoor"
    assert infer_use("Etwas für mich") is None
