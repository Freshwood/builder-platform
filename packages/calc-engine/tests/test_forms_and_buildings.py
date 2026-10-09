"""Free forms, members, carpentry joints, bulk materials and buildings (ADR-0007)."""

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from calc_engine.assembly import shapes
from calc_engine.assembly.templates import templates
from calc_engine.engine import DesignRejectedError, default_engine
from construction_model.assembly import AssemblyDesign
from construction_model.model import ConstructionResult, ProjectInputs

engine = default_engine()


def build(design: AssemblyDesign | dict[str, Any], **params: Any) -> ConstructionResult:
    if isinstance(design, dict):
        design = AssemblyDesign.model_validate(design)
    return engine.build(ProjectInputs(title="t", pack_id="design", params=params, design=design))


def frame(parts: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    """A design with a sill and a plate 1000 mm apart; ``parts`` go in between."""
    return {
        "object_type": "Rahmen",
        "summary": "Rahmen",
        "params": [],
        "parts": [
            {
                "id": "sill",
                "name": "Schwelle",
                "material": "lumber_oak_beam_160x160",
                "size": [2000, 160, 160],
                "at": [0, 0, 0],
            },
            {
                "id": "post",
                "name": "Ständer",
                "material": "lumber_oak_beam_160x160",
                "size": [160, 160, 1000],
                "at": [0, 0, 160],
                "repeat": {"count": 2},
            },
            {
                "id": "plate",
                "name": "Rähm",
                "material": "lumber_oak_beam_160x160",
                "size": [2000, 160, 160],
                "at": [0, 0, 1160],
            },
            *parts,
        ],
        **extra,
    }


def two_posts(design: dict[str, Any]) -> dict[str, Any]:
    design["parts"][1]["at"] = ["i * 1840", 0, 160]
    return design


BRACE = {
    "id": "brace",
    "name": "Strebe",
    "material": "lumber_oak_beam_160x160",
    "start": [160, 80, 160],
    "end": [1840, 80, 1160],
    "cuts": ["corner", "corner"],
}


# --- 2D shapes ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ring",
    [
        shapes.cloud(750, 500, None),
        shapes.cloud(1200, 350, 6),
        shapes.ellipse(400, 300),
        shapes.arch(800, 1200),
        shapes.rounded(600, 300, 50),
        shapes.triangle(6000, 3000, None),
    ],
)
def test_generated_outlines_fill_their_box_and_triangulate_exactly(ring: shapes.Ring) -> None:
    x0, y0, x1, y1 = shapes.bbox(ring)
    assert (round(x0), round(y0)) == (0, 0)
    hole = shapes.ellipse(60, 40, x1 / 2 - 30, y1 / 2 - 20)
    assert not shapes.check_holes(ring, [hole])
    tris = shapes.triangulate(ring, [hole])
    covered = sum(abs(shapes.signed_area(list(t))) for t in tris)
    assert covered == pytest.approx(shapes.area(ring, [hole]), rel=1e-6)


def test_cloud_has_a_flat_bottom() -> None:
    ring = shapes.cloud(750, 500, None)
    bottom = [p for p in ring if p[1] < 0.5]
    assert max(p[0] for p in bottom) - min(p[0] for p in bottom) > 200


def test_cutout_outside_the_contour_is_rejected() -> None:
    errors = shapes.check_holes(shapes.rect(100, 100), [shapes.rect(20, 20, 90, 10)])
    assert errors
    assert "nicht vollständig innerhalb" in errors[0]


# --- Members and joints -------------------------------------------------------------------


def test_member_with_corner_cuts_fits_the_field() -> None:
    design = two_posts(
        frame(
            [BRACE],
            joints=[
                {"kind": "tenon", "part": "post", "into": "sill"},
                {"kind": "tenon", "part": "post", "into": "plate"},
                {"kind": "tenon", "part": "brace", "into": "sill"},
                {"kind": "tenon", "part": "brace", "into": "plate"},
            ],
            auto_screws=False,
        )
    )
    r = build(design)
    brace = next(c for c in r.cut_list if c.part == "Strebe")
    # Diagonal of the 1680 × 1000 field plus a tenon at each end; angled ends noted.
    assert brace.note is not None
    assert "Klaue / Klaue" in brace.note
    assert "inkl. 120 mm Zapfen" in brace.note
    assert 2000 < brace.length_mm < 2200
    assert any(line.item_id == "peg_oak_22" and line.quantity == 6 for line in r.bom)
    assert any(s.mesh is not None for s in r.solids)
    assert any(step.title == "Holzverbindungen anreißen und ausarbeiten" for step in r.instructions)


def test_overlap_needs_a_declared_joint() -> None:
    crossing = {
        "id": "cross",
        "name": "Kreuz",
        "material": "lumber_oak_beam_160x160",
        "size": [160, 160, 1000],
        "at": [920, 0, 160],
    }
    lap = {
        "id": "lap",
        "name": "Riegel",
        "material": "lumber_oak_beam_160x160",
        "size": [1680, 160, 160],
        "at": [160, 0, 500],
    }
    with pytest.raises(DesignRejectedError, match="durchdringen sich"):
        build(two_posts(frame([crossing, lap])))
    r = build(
        two_posts(
            frame([crossing, lap], joints=[{"kind": "half_lap", "part": "lap", "into": "cross"}])
        )
    )
    assert any("Blatt" in d for s in r.instructions for d in s.details)


def test_joint_between_parts_that_never_touch_is_rejected() -> None:
    with pytest.raises(DesignRejectedError, match="berühren sich nirgends"):
        build(two_posts(frame([], joints=[{"kind": "tenon", "part": "sill", "into": "plate"}])))


def test_level_cut_on_a_horizontal_member_is_rejected() -> None:
    beam = {
        "id": "beam",
        "name": "Balken",
        "material": "lumber_oak_beam_160x160",
        "start": [0, 80, 1400],
        "end": [2000, 80, 1400],
        "cuts": ["level", "square"],
    }
    with pytest.raises(DesignRejectedError, match="Waagschnitt"):
        build(two_posts(frame([beam])))


# --- Shapes, cutouts and bulk materials ---------------------------------------------------


def test_cloud_shelf_gets_a_template_drawing_and_jigsaw() -> None:
    r = build(templates()["cloud_shelf"].design)
    assert "template_2" in {d.view for d in r.drawings}
    cloud = next(c for c in r.cut_list if c.part == "Rückwand Wolke")
    assert cloud.note == "Kontur nach Schablone aussägen"
    assert any("Stichsäge" in t.name for t in r.tools)


def test_bulk_material_is_priced_by_volume_and_area() -> None:
    design = {
        "object_type": "Mauer",
        "summary": "Mauer",
        "category": "building",
        "use": "outdoor",
        "params": [],
        "parts": [
            {
                "id": "footing",
                "name": "Fundament",
                "material": "concrete_c25",
                "size": [2000, 400, 800],
                "at": [0, 0, -800],
            },
            {
                "id": "wall",
                "name": "Wand",
                "material": "infill_clay",
                "size": [2000, 160, 1000],
                "at": [0, 120, 0],
                "cutouts": [{"kind": "rect", "at": [600, 200], "size": [800, 600]}],
            },
        ],
        "auto_screws": False,
    }
    r = build(design)
    lines = {line.item_id: line for line in r.bom}
    # 0.64 m³ concrete, 0.2432 m³ masonry (2 m × 1 m × 0.16 m minus the opening) +5 %.
    assert str(lines["concrete_c25"].quantity) == "0.7"
    assert str(lines["infill_clay"].quantity) == "0.3"
    assert "BUILDING" in {n.code for n in r.notices}


def test_only_concrete_may_go_below_ground() -> None:
    design = two_posts(frame([], category="building"))
    design["parts"][0]["at"] = [0, 0, -100]
    with pytest.raises(DesignRejectedError, match="nur Fundamente aus Beton"):
        build(design)


def test_objects_keep_their_size_limit() -> None:
    design = two_posts(frame([]))
    design["parts"][0]["size"] = [4500, 160, 160]
    with pytest.raises(DesignRejectedError, match='category="building"'):
        build(design)


# --- Templates ----------------------------------------------------------------------------


@settings(max_examples=12, deadline=None)
@given(
    width=st.integers(500, 1200),
    height=st.integers(350, 1000),
    depth=st.integers(100, 250),
    shelves=st.integers(1, 4),
    material=st.sampled_from(["plywood_birch_18", "glulam_spruce_18"]),
    support=st.sampled_from(["floor", "wall"]),
)
def test_cloud_shelf_is_valid_for_all_parameters(
    width: int, height: int, depth: int, shelves: int, material: str, support: str
) -> None:
    """Valid standing and wall-mounted (create_from_template applies support from the brief)."""
    r = build(
        templates()["cloud_shelf"].design.model_copy(update={"support": support}),
        width_mm=width,
        height_mm=height,
        depth_mm=depth,
        shelves=shelves,
        material=material,
    )
    assert r.key_figures["Außenmaße (B × T × H)"] == f"{width} × {depth} × {height} mm"


@settings(max_examples=6, deadline=None)
@given(
    length=st.integers(5000, 10000),
    depth=st.integers(4000, 8000),
    wall=st.integers(2600, 3200),
    roof=st.integers(1500, 4500),
    bays_x=st.integers(3, 6),
    bays_y=st.integers(3, 5),
)
def test_timber_frame_house_is_valid_for_all_parameters(
    length: int, depth: int, wall: int, roof: int, bays_x: int, bays_y: int
) -> None:
    r = build(
        templates()["timber_frame_house"].design,
        length_mm=length,
        depth_mm=depth,
        wall_mm=wall,
        roof_mm=roof,
        bays_x=bays_x,
        bays_y=bays_y,
    )
    assert "BUILDING" in {n.code for n in r.notices}


def test_timber_frame_house_is_complete() -> None:
    r = build(templates()["timber_frame_house"].design)
    items = {line.item_id for line in r.bom}
    assert {
        "concrete_c25",
        "infill_clay",
        "roof_tiles_clay",
        "cladding_larch_24",
        "window_wood_800x1000",
        "door_wood_1000x2100",
        "peg_oak_22",
        "screw_timber_8x240_50",
    } <= items
    parts = {c.part for c in r.cut_list}
    assert {
        "Schwelle Traufseite",
        "Ständer Traufseite",
        "Strebe Traufseite",
        "Sparren vorne",
    } <= parts
    assert r.key_figures["Gründungstiefe"] == "800 mm"
