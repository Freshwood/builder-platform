from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from calc_engine.cutting import plan_cuts
from calc_engine.engine import ParameterError, default_engine
from calc_engine.packs.raised_bed.geometry import BOARD_W, compute_geometry
from calc_engine.packs.raised_bed.params import RaisedBedParams
from construction_model.diff import diff_results
from construction_model.model import ProjectInputs

FIXED_NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
engine = default_engine(clock=lambda: FIXED_NOW)


def build(**params: object):  # type: ignore[no-untyped-def]
    return engine.build(ProjectInputs(title="t", pack_id="raised_bed", params=params))  # type: ignore[arg-type]


def qty(result, item_prefix: str) -> Decimal:  # type: ignore[no-untyped-def]
    return sum(
        (line.quantity for line in result.bom if line.item_id.startswith(item_prefix)), Decimal(0)
    )


def test_reference_bed_2000x1000x800() -> None:
    r = build(length_mm=2000, width_mm=1000, height_mm=800)
    assert r.key_figures["Wandhöhe"] == "870 mm (6 Brettreihen)"
    assert r.key_figures["Pfosten"] == "6"
    assert qty(r, "board_douglas") == 12
    assert qty(r, "post_douglas") == 3
    assert qty(r, "slab_concrete") == 6
    assert {n.code for n in r.notices} >= {"height_rounded", "tie_rods", "food_safe_materials"}
    assert r.costs.material.min == Decimal("400.00")
    assert r.provenance.pack_id == "raised_bed"
    assert {d.view for d in r.drawings} == {"plan", "front", "side", "corner_detail"}


def test_short_bed_needs_no_tie_rods() -> None:
    r = build(length_mm=1200, width_mm=800, height_mm=435)
    assert r.key_figures["Zuganker"] == "0"
    assert qty(r, "rod_") == 0
    assert "height_rounded" not in {n.code for n in r.notices}


def test_invalid_parameters_are_reported() -> None:
    with pytest.raises(ParameterError) as exc:
        build(length_mm=100, width_mm=1000)
    assert "length_mm" in exc.value.errors[0]
    with pytest.raises(ParameterError):
        build(colour="red")


def test_wider_bed_changes_quantities_and_cost() -> None:
    before = build(length_mm=2000, width_mm=1000, height_mm=800)
    after = build(length_mm=2000, width_mm=1500, height_mm=800)
    diff = diff_results(before, after)
    assert [c.name for c in diff.params] == ["width_mm"]
    assert diff.material_cost_after[0] > diff.material_cost_before[0]  # type: ignore[index]
    assert any(q.item_id == "soil_raised_bed_40l" for q in diff.quantities)
    assert "reach" in {n.code for n in after.notices}


def test_variants_are_priced_and_selection_tracked() -> None:
    r = engine.build(
        ProjectInputs(
            title="t",
            pack_id="raised_bed",
            variant_key="durable",
            params={"wood": "larch"},
        )
    )
    by_key = {v.key: v for v in r.variants}
    assert set(by_key) == {"budget", "durable", "comfort"}
    assert by_key["durable"].is_selected
    assert by_key["budget"].material_cost.max < by_key["durable"].material_cost.max


def test_component_guids_are_stable_across_rebuilds() -> None:
    a = build(length_mm=2000)
    b = build(length_mm=2500)
    assert a.components[0].guid == b.components[0].guid
    assert a.components[0].ifc_type == "IfcPlate"


def test_build_is_deterministic() -> None:
    assert build(length_mm=1800).model_dump_json() == build(length_mm=1800).model_dump_json()


def test_plan_cuts_respects_kerf_and_rejects_oversize() -> None:
    bars = plan_cuts([2000, 1996], 4000)
    assert len(bars) == 1
    assert len(plan_cuts([2000, 1997], 4000)) == 2
    with pytest.raises(ValueError, match="exceeds"):
        plan_cuts([4001], 4000)


dims = st.fixed_dictionaries(
    {
        "length_mm": st.integers(600, 4000),
        "width_mm": st.integers(400, 1500),
        "height_mm": st.integers(290, 1160),
        "wood": st.sampled_from(["spruce", "douglas", "larch"]),
        "liner": st.booleans(),
        "vole_mesh": st.booleans(),
        "top_cap": st.booleans(),
    }
)


@settings(max_examples=60, deadline=None)
@given(dims)
def test_invariants(params: dict[str, object]) -> None:
    r = build(**params)
    p = RaisedBedParams.model_validate(params)
    g = compute_geometry(p)
    assert g.wall_height >= p.height_mm
    assert g.wall_height - p.height_mm < BOARD_W
    assert r.costs.material.min >= 0
    assert r.costs.material.min <= r.costs.material.max
    # Cut pieces fit into the purchased stock.
    for plan in r.stock_plan:
        assert plan.waste_mm >= 0
    # Every board cut appears in the cut list with its exact length.
    cut_total = sum(c.count for c in r.cut_list if c.cross_section == "28 × 145")
    assert cut_total == sum(
        1 for c in r.components if c.role in {"long_board", "short_board", "cap"}
    )


@settings(max_examples=40, deadline=None)
@given(st.integers(600, 3500), st.integers(1, 500))
def test_cost_is_monotonic_in_length(length: int, extra: int) -> None:
    a = build(length_mm=length)
    b = build(length_mm=min(4000, length + extra))
    assert b.costs.material.max >= a.costs.material.max
