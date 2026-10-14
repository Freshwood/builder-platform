"""Door bay of the timber frame house fixture design across the critical bay widths.

The door bay is only one bay wide when the infill beside the door meets the 80 mm minimum of the
infill materials (bay >= 1000 + 160 + 2 * 80 = 1320 mm). Narrower bays merge two neighbouring
bays into one door opening, so every parameter combination still builds with exactly one door.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from calc_engine.assembly.resolve import resolve_parts, validate_params
from calc_engine.engine import default_engine
from construction_model.model import ConstructionResult, ProjectInputs

# --import-mode=importlib does not add this directory to sys.path (see corpus.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from design_fixtures import fixture_design

DOOR = "door_wood_1000x2100"
WINDOW = "window_wood_800x1000"
INFILL_MIN_MM = 80
POST_MM = 160

engine = default_engine()
design = fixture_design("timber_frame_house")


def _build(**params: float | str) -> ConstructionResult:
    return engine.build(ProjectInputs(title="t", params=params, design=design))


def _quantity(result: ConstructionResult, item_id: str) -> int:
    return sum(int(line.quantity) for line in result.bom if line.item_id == item_id)


@pytest.mark.parametrize("bays_x", [4, 6])
@pytest.mark.parametrize("bay_mm", range(1200, 1401, 10))
def test_door_bay_builds_across_the_threshold(bays_x: int, bay_mm: int) -> None:
    """Bay widths around the door threshold build with one door and consistent windows."""
    length = 400 + bays_x * bay_mm
    result = _build(length_mm=length, bays_x=bays_x)

    door_bays = 1 if bay_mm >= 1320 else 2
    assert _quantity(result, DOOR) == 1
    # Both long sides carry a window in every interior bay that is wide enough, except door bays.
    windows = 2 * (bays_x - 2) - door_bays if bay_mm >= 1160 else 0
    assert _quantity(result, WINDOW) == windows

    parts = resolve_parts(design, validate_params(design, {"length_mm": length, "bays_x": bays_x}))
    ids = [p.spec_id for p in parts]
    assert ids.count("door") == 1
    assert ids.count("fill_door_side") == 2
    assert ids.count("fill_door_top") == 1
    # A merged door opening drops the post between its two bays.
    assert ids.count("post_x") == 2 * (bays_x + 1) - (door_bays - 1)
    for part in parts:
        if part.spec_id == "fill_door_side":
            assert part.size[0] >= INFILL_MIN_MM
    door = next(p for p in parts if p.spec_id == "door")
    opening = door_bays * bay_mm - POST_MM
    assert opening >= door.size[0] + 2 * INFILL_MIN_MM


@pytest.mark.parametrize("bays_x", range(3, 7))
@pytest.mark.parametrize("length", [5000, 7500, 10000])
def test_door_present_over_the_parameter_range(bays_x: int, length: int) -> None:
    """Even the narrowest bays (6 bays on 5 m) keep a door."""
    assert _quantity(_build(length_mm=length, bays_x=bays_x), DOOR) == 1
