"""Deterministic geometry and quantities of a raised bed.

Construction: horizontal boards screwed to square posts in the inside corners. Long side boards
run the full outer length; short side boards sit between them. Intermediate post pairs with
threaded tie rods limit the free span against soil pressure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from calc_engine.packs.raised_bed.params import RaisedBedParams

BOARD_T = 28
BOARD_W = 145
POST = 70
BOARD_STOCK = 4000
POST_STOCK = 2500
MAX_FREE_SPAN = 1500
TIE_TWO_LEVELS_FROM = 600
TIE_ALLOWANCE = 60
LINER_TOP_GAP = 50
LINER_OVERLAP = 200
LINER_ROLL_LENGTH = 5000
MESH_ROLL_WIDTH = 1000
MESH_ROLL_LENGTH = 5000
MESH_EDGE = 100
SCREWS_PER_JOINT = 2
FILL_TOP_GAP = 50
SOIL_BAG_L = 40
MIN_SOIL_LAYER = 200


@dataclass(frozen=True)
class FillPlan:
    name: str
    thickness_mm: int
    purchase: bool


@dataclass(frozen=True)
class RaisedBedGeometry:
    p: RaisedBedParams
    rows: int
    wall_height: int
    total_height: int
    inner_length: int
    inner_width: int
    mid_positions: tuple[int, ...]
    tie_levels: int
    tie_rod_length: int
    liner_height: int
    liner_running_length: int
    liner_roll_width: int
    liner_strips_per_roll: int
    mesh_strips: int
    mesh_strip_length: int
    fill_height: int
    fill: tuple[FillPlan, ...]

    @property
    def mid_count(self) -> int:
        return len(self.mid_positions)

    @property
    def post_count(self) -> int:
        return 4 + 2 * self.mid_count

    @property
    def post_length(self) -> int:
        return self.wall_height

    @property
    def tie_rod_count(self) -> int:
        return self.mid_count * self.tie_levels

    @property
    def wall_screws(self) -> int:
        corner = 4 * self.rows * 2 * SCREWS_PER_JOINT
        mid = 2 * self.mid_count * self.rows * SCREWS_PER_JOINT
        return corner + mid

    @property
    def cap_screws(self) -> int:
        if not self.p.top_cap:
            return 0
        return 4 * 2 * SCREWS_PER_JOINT + 2 * self.mid_count * SCREWS_PER_JOINT

    @property
    def short_board_length(self) -> int:
        return self.p.width_mm - 2 * BOARD_T

    @property
    def cap_short_length(self) -> int:
        return self.p.width_mm - 2 * BOARD_W

    def fill_volume_l(self, thickness_mm: int) -> int:
        return round(self.inner_length * self.inner_width * thickness_mm / 1_000_000)

    @property
    def total_fill_l(self) -> int:
        return self.fill_volume_l(self.fill_height)

    @property
    def footprint_m2(self) -> float:
        return self.p.length_mm * self.p.width_mm / 1_000_000

    @property
    def planting_area_m2(self) -> float:
        return self.inner_length * self.inner_width / 1_000_000


def _fill_layers(fill_height: int) -> tuple[FillPlan, ...]:
    if fill_height < 450:
        soil = max(MIN_SOIL_LAYER, fill_height * 2 // 3)
        soil = min(soil, fill_height)
        compost = fill_height - soil
        layers = [FillPlan("Grobkompost", compost, False), FillPlan("Hochbeeterde", soil, True)]
    else:
        soil = max(MIN_SOIL_LAYER, round(fill_height * 0.25))
        compost = round(fill_height * 0.2)
        leaves = round(fill_height * 0.2)
        branches = fill_height - soil - compost - leaves
        layers = [
            FillPlan("Äste und Strauchschnitt", branches, False),
            FillPlan("Laub, Rasensoden (umgedreht)", leaves, False),
            FillPlan("Grobkompost", compost, False),
            FillPlan("Hochbeeterde", soil, True),
        ]
    return tuple(layer for layer in layers if layer.thickness_mm > 0)


def compute_geometry(p: RaisedBedParams) -> RaisedBedGeometry:
    rows = math.ceil(p.height_mm / BOARD_W)
    wall_height = rows * BOARD_W
    inner_length = p.length_mm - 2 * BOARD_T
    inner_width = p.width_mm - 2 * BOARD_T

    mid_count = max(0, math.ceil(inner_length / MAX_FREE_SPAN) - 1)
    # Evenly spaced intermediate post centres, measured from the outer left edge.
    mid_positions = tuple(round(p.length_mm * (i + 1) / (mid_count + 1)) for i in range(mid_count))
    tie_levels = 2 if wall_height > TIE_TWO_LEVELS_FROM else 1

    liner_height = wall_height - LINER_TOP_GAP
    liner_roll_width = 1000 if liner_height <= 1000 else 1500
    liner_strips_per_roll = max(1, liner_roll_width // liner_height)
    liner_running = 2 * (inner_length + inner_width) + LINER_OVERLAP

    mesh_strips = math.ceil((inner_width + 2 * MESH_EDGE) / MESH_ROLL_WIDTH)
    mesh_strip_length = inner_length + 2 * MESH_EDGE

    fill_height = wall_height - FILL_TOP_GAP
    return RaisedBedGeometry(
        p=p,
        rows=rows,
        wall_height=wall_height,
        total_height=wall_height + (BOARD_T if p.top_cap else 0),
        inner_length=inner_length,
        inner_width=inner_width,
        mid_positions=mid_positions,
        tie_levels=tie_levels,
        tie_rod_length=p.width_mm + TIE_ALLOWANCE,
        liner_height=liner_height,
        liner_running_length=liner_running,
        liner_roll_width=liner_roll_width,
        liner_strips_per_roll=liner_strips_per_roll,
        mesh_strips=mesh_strips,
        mesh_strip_length=mesh_strip_length,
        fill_height=fill_height,
        fill=_fill_layers(fill_height),
    )
