from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from calc_engine.assembly.expr import ExprError, evaluate
from calc_engine.assembly.sheets import plan_sheets
from calc_engine.assembly.templates import templates
from calc_engine.engine import DesignRejectedError, default_engine
from construction_model.assembly import AssemblyDesign
from construction_model.commands import ChangeParameterBy, ReplaceDesign, apply_to_inputs
from construction_model.model import ConstructionResult, ProjectInputs

FIXED_NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
engine = default_engine(clock=lambda: FIXED_NOW)


def build(design: AssemblyDesign | dict[str, Any], **params: Any) -> ConstructionResult:
    if isinstance(design, dict):
        design = AssemblyDesign.model_validate(design)
    return engine.build(ProjectInputs(title="t", pack_id="design", params=params, design=design))


def table(**overrides: Any) -> dict[str, Any]:
    """A minimal side table: four legs and a top."""
    design: dict[str, Any] = {
        "object_type": "Beistelltisch",
        "summary": "Beistelltisch",
        "params": [
            {
                "name": "width_mm",
                "label": "Breite",
                "kind": "length",
                "default": 600,
                "min": 300,
                "max": 1200,
            },
            {
                "name": "height_mm",
                "label": "Höhe",
                "kind": "length",
                "default": 500,
                "min": 300,
                "max": 800,
            },
        ],
        "parts": [
            {
                "id": "leg",
                "name": "Bein",
                "material": "frame_spruce_44x44",
                "size": [44, 44, "height_mm - 18"],
                "at": ["(i % 2) * (width_mm - 44)", "(i // 2) * (400 - 44)", 0],
                "repeat": {"count": 4},
            },
            {
                "id": "top",
                "name": "Platte",
                "material": "glulam_spruce_18",
                "size": ["width_mm", 400, 18],
                "at": [0, 0, "height_mm - 18"],
            },
        ],
    }
    design.update(overrides)
    return design


def test_minimal_design_builds_everything() -> None:
    r = build(table())
    assert r.trust == "ai_draft"
    assert r.key_figures["Außenmaße (B × T × H)"] == "600 × 400 × 500 mm"
    assert [c.position for c in r.cut_list] == [1, 2]
    assert r.cut_list[0].count == 4
    assert r.cut_list[0].length_mm == 482
    assert r.cut_list[1].width_mm == 400
    # Four legs of 482 mm fit on one 2000 mm bar
    plan = next(s for s in r.stock_plan if s.item_id.startswith("frame_spruce_44x44"))
    assert plan.stock_count == 1
    assert plan.stock_length_mm == 2000
    assert sorted(plan.bars[0]) == [482, 482, 482, 482]
    assert any(line.item_id.startswith("screw_zn_") for line in r.bom)
    assert {d.view for d in r.drawings} == {"iso", "front", "side", "plan"}
    assert len(r.solids) == 5
    assert {n.code for n in r.notices} >= {"AI_DRAFT", "NO_STATICS"}
    assert r.costs.material.min > 0
    assert [p.name for p in r.param_specs] == ["width_mm", "height_mm"]


def test_parameters_drive_geometry() -> None:
    small, large = build(table(), width_mm=400), build(table(), width_mm=1000)
    assert small.key_figures["Außenmaße (B × T × H)"].startswith("400 ×")
    # Both still need one sheet and one bar, but the surface (finish, weight) grows
    assert large.key_figures["Holzoberfläche"] != small.key_figures["Holzoberfläche"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"material": "unobtainium"}, "unbekanntes Material"),
        ({"size": [50, 44, 400]}, "passen nicht zum Querschnitt"),
        ({"size": [44, 44, 3000]}, "Handelslänge"),
        ({"at": [10, 0, 0]}, "durchdringen sich"),
        ({"at": [0, 0, 20]}, "nicht alle bauteile sind verbunden"),
    ],
)
def test_engine_rejects_broken_designs(change: dict[str, Any], message: str) -> None:
    design = table()
    leg = {**design["parts"][0], **change}
    if "at" in change:
        leg.pop("repeat")
        leg["id"] = "extra"
        design["parts"] = [*design["parts"], leg]
    else:
        design["parts"] = [leg, design["parts"][1]]
    with pytest.raises(DesignRejectedError) as exc:
        build(design)
    assert message in " ".join(exc.value.errors).lower() or message in " ".join(exc.value.errors)


def test_floating_design_is_rejected() -> None:
    design = table()
    design["parts"] = [
        {**p, "at": [p["at"][0], p["at"][1], f"({p['at'][2]}) + 50"]} for p in design["parts"]
    ]
    with pytest.raises(DesignRejectedError, match="Boden"):
        build(design)


def test_size_limit_for_free_designs() -> None:
    design = table()
    design["parts"][1] |= {
        "size": [1500, 400, 18],
        "at": ["i * 1500", 0, "height_mm - 18"],
        "repeat": {"count": 3},
    }
    with pytest.raises(DesignRejectedError, match="Fachplanung"):
        build(design)


def test_parameter_bounds_are_enforced() -> None:
    with pytest.raises(DesignRejectedError, match="zwischen"):
        build(table(), width_mm=5000)
    with pytest.raises(DesignRejectedError, match="unbekannter Parameter"):
        build(table(), colour="red")


@pytest.mark.parametrize("key", sorted(templates()))
def test_templates_build_with_defaults_and_variants(key: str) -> None:
    tpl = templates()[key]
    r = build(tpl.design)
    assert r.trust == "template"
    assert r.variants, "templates offer variants"
    assert all(v.material_cost.min > 0 for v in r.variants)
    assert r.instructions[0].title == "Material besorgen und zuschneiden"


@settings(max_examples=25, deadline=None)
@given(
    width=st.integers(400, 1400),
    depth=st.integers(200, 590),
    height=st.integers(600, 2000),
    shelves=st.integers(2, 9),
    back=st.booleans(),
)
def test_shelf_is_valid_for_all_parameters(
    width: int, depth: int, height: int, shelves: int, back: bool
) -> None:
    design = templates()["shelf"].design
    r = build(
        design, width_mm=width, depth_mm=depth, height_mm=height, shelves=shelves, back_panel=back
    )
    assert r.key_figures["Außenmaße (B × T × H)"] == f"{width} × {depth} × {height} mm"
    shelf = next(c for c in r.cut_list if c.part == "Fachboden")
    assert shelf.count == shelves


def test_tall_shelf_gets_tip_protection() -> None:
    r = build(templates()["shelf"].design, height_mm=2000, depth_mm=250)
    assert any(line.item_id == "wall_anchor_set" for line in r.bom)
    assert "TIP" in {n.code for n in r.notices}


def test_outdoor_bench_uses_stainless_screws_and_no_glue() -> None:
    r = build(templates()["garden_bench"].design)
    items = {line.item_id for line in r.bom}
    assert any(i.startswith("screw_a2_") for i in items)
    assert not any(i.startswith("screw_zn_") for i in items)
    assert "glue_d3_750" not in items


def test_bench_without_backrest_is_cheaper() -> None:
    design = templates()["garden_bench"].design
    assert build(design, backrest=False).costs.material.max < build(design).costs.material.max


def test_change_parameter_by_falls_back_to_design_default() -> None:
    design = templates()["workbench"].design
    inputs = ProjectInputs(title="t", pack_id="design", params={}, design=design)
    changed = apply_to_inputs(inputs, ChangeParameterBy(name="width_mm", delta=300))
    assert changed.params["width_mm"] == 1800


def test_replace_design_keeps_valid_parameters() -> None:
    design = templates()["shelf"].design
    inputs = ProjectInputs(
        title="t", pack_id="design", params={"width_mm": 1300, "shelves": 4}, design=design
    )
    narrower = design.model_copy(
        update={
            "params": [
                p.model_copy(update={"max": 1000}) if p.name == "width_mm" else p
                for p in design.params
            ]
        }
    )
    replaced = apply_to_inputs(inputs, ReplaceDesign(design=narrower))
    assert replaced.params == {"shelves": 4}


def test_expressions() -> None:
    env = {"w": 800.0, "n": 3.0, "flag": 1.0}
    assert evaluate("w - 2 * 18", env) == 764
    assert evaluate("if(w > 500, 1, 2)", env) == 1
    assert evaluate("max(w, 900) // 100", env) == 9
    assert evaluate("flag and n >= 3", env) == 1
    assert evaluate(12, env) == 12
    for bad in ("__import__('os')", "w.real", "[1, 2]", "unknown + 1", "w / 0"):
        with pytest.raises(ExprError):
            evaluate(bad, env)


def test_sheet_planning() -> None:
    sheets = plan_sheets([(1800, 297), (1800, 297), (764, 297)], (2000, 600))
    assert len(sheets) == 2
    assert sum(s.used_area for s in sheets) == 2 * 1800 * 297 + 764 * 297


def test_solids_match_cut_list_quantities() -> None:
    r = build(templates()["workbench"].design, castors=True)
    pieces = sum(c.count for c in r.cut_list)
    castors = sum(1 for s in r.solids if s.name == "Lenkrolle")
    assert castors == 4
    assert pieces + castors == len(r.solids)
    assert sum((line.total.min for line in r.bom), Decimal(0)) == r.costs.material.min


@settings(max_examples=25, deadline=None)
@given(
    length=st.integers(800, 2400),
    seat=st.integers(380, 500),
    slats=st.integers(2, 4),
    backrest=st.booleans(),
    wood=st.sampled_from(["douglas", "larch"]),
)
def test_bench_is_valid_for_all_parameters(
    length: int, seat: int, slats: int, backrest: bool, wood: str
) -> None:
    r = build(
        templates()["garden_bench"].design,
        length_mm=length,
        seat_height_mm=seat,
        slats=slats,
        backrest=backrest,
        wood=wood,
    )
    assert r.key_figures["Außenmaße (B × T × H)"].startswith(f"{length} ×")


@settings(max_examples=25, deadline=None)
@given(
    width=st.integers(800, 2000),
    depth=st.integers(500, 900),
    height=st.integers(750, 1050),
    shelf=st.booleans(),
    castors=st.booleans(),
)
def test_workbench_is_valid_for_all_parameters(
    width: int, depth: int, height: int, shelf: bool, castors: bool
) -> None:
    r = build(
        templates()["workbench"].design,
        width_mm=width,
        depth_mm=depth,
        height_mm=height,
        lower_shelf=shelf,
        castors=castors,
    )
    assert r.key_figures["Außenmaße (B × T × H)"] == f"{width} × {depth} × {height} mm"
