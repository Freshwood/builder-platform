"""Drawings for free-form designs: orthographic views and an isometric view with callouts.

Every view is a parallel projection of the part boxes. Visible faces become filled polygons
(material tone plus light), painted back to front. For non-overlapping axis-aligned boxes the
order is exact (separating planes); rotated parts fall back to centre depth.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from itertools import combinations, pairwise

from calc_engine.assembly.geometry import Box, Vec
from construction_model.drawing import (
    Callout,
    Dimension,
    Drawing,
    LegendEntry,
    Polygon,
    Primitive,
)
from construction_model.model import Solid

_S2, _S3, _S6 = math.sqrt(2), math.sqrt(3), math.sqrt(6)
_LIGHT = (0.32, -0.55, 0.77)
_SEP_TOL = 0.5


@dataclass(frozen=True)
class View:
    key: str
    title: str
    camera: Vec
    """Unit vector pointing from the object towards the viewer."""
    right: Vec
    up: Vec
    dims: tuple[str, str] | None
    """Axis names measured horizontally and vertically, or None (no dimensions)."""
    chain: str | None = None
    """Axis whose extent selects horizontal parts for the level chain (x or y)."""


VIEWS = (
    View(
        "iso",
        "Isometrie mit Positionsnummern",
        (1 / _S3, -1 / _S3, 1 / _S3),
        (1 / _S2, 1 / _S2, 0.0),
        (-1 / _S6, 1 / _S6, 2 / _S6),
        None,
    ),
    View(
        "front",
        "Vorderansicht",
        (0.0, -1.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        ("x", "z"),
        "x",
    ),
    View(
        "side",
        "Seitenansicht (rechts)",
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
        ("y", "z"),
        "y",
    ),
    View("plan", "Draufsicht", (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), ("x", "y")),
)
# Wall-mounted objects carry battens, hinges and latches on the wall side; show it as well.
WALL_SIDE_VIEWS = (
    View(
        "iso_back",
        "Isometrie Wandseite mit Positionsnummern",
        (-1 / _S3, 1 / _S3, 1 / _S3),
        (-1 / _S2, -1 / _S2, 0.0),
        (1 / _S6, -1 / _S6, 2 / _S6),
        None,
    ),
    View(
        "back",
        "Rückansicht (Wandseite)",
        (0.0, 1.0, 0.0),
        (-1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
        ("x", "z"),
        "x",
    ),
)
_AXIS = {"x": 0, "y": 1, "z": 2}


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _project(p: Vec, view: View) -> tuple[float, float]:
    return (round(_dot(p, view.right), 2), round(-_dot(p, view.up), 2))


def _shade(normal: Vec) -> float:
    return round(0.62 + 0.38 * max(0.0, _dot(normal, _LIGHT)), 3)


def _paint_order(boxes: list[Box], view: View) -> list[int]:
    """Back-to-front order: topological sort of 'is behind' among overlapping projections."""
    n = len(boxes)
    bounds = [b.bounds() for b in boxes]
    depth = [_dot(b.center(), view.camera) for b in boxes]
    flat: list[tuple[float, float, float, float]] = []
    for b in boxes:
        pts = [_project(p, view) for p in b.corners()]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        flat.append((min(xs), max(xs), min(ys), max(ys)))
    after: list[list[int]] = [[] for _ in range(n)]
    indegree = [0] * n
    for i, j in combinations(range(n), 2):
        fi, fj = flat[i], flat[j]
        if fi[1] <= fj[0] + 0.01 or fj[1] <= fi[0] + 0.01:
            continue
        if fi[3] <= fj[2] + 0.01 or fj[3] <= fi[2] + 0.01:
            continue
        behind = _behind(bounds[i], bounds[j], view.camera, boxes[i].rotated or boxes[j].rotated)
        if behind is None:
            behind = depth[i] <= depth[j]
        first, second = (i, j) if behind else (j, i)
        after[first].append(second)
        indegree[second] += 1
    heap = [(depth[i], i) for i in range(n) if indegree[i] == 0]
    heapq.heapify(heap)
    order: list[int] = []
    done = [False] * n
    while len(order) < n:
        if not heap:
            # Cycle (only possible with rotated parts): break it at the farthest remaining box.
            rest = min((depth[i], i) for i in range(n) if not done[i])
            indegree[rest[1]] = 0
            heap.append(rest)
        _, i = heapq.heappop(heap)
        if done[i]:
            continue
        done[i] = True
        order.append(i)
        for k in after[i]:
            indegree[k] -= 1
            if indegree[k] == 0 and not done[k]:
                heapq.heappush(heap, (depth[k], k))
    return order


def _behind(a: tuple[Vec, Vec], b: tuple[Vec, Vec], camera: Vec, approx: bool) -> bool | None:
    """True if box a is behind b, False if in front, None if undetermined."""
    if approx:
        return None
    (alo, ahi), (blo, bhi) = a, b
    for k in range(3):
        if abs(camera[k]) < 1e-9:
            continue
        if ahi[k] <= blo[k] + _SEP_TOL:
            return camera[k] > 0
        if bhi[k] <= alo[k] + _SEP_TOL:
            return camera[k] < 0
    return None


def _area(points: list[tuple[float, float]]) -> float:
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True):
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


def _centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    return (
        round(sum(p[0] for p in points) / len(points), 2),
        round(sum(p[1] for p in points) / len(points), 2),
    )


def _levels(boxes: list[Box], axis: int, extent: float) -> list[float]:
    """Top surfaces of flat, wide parts (shelves, seats) for a dimension chain."""
    levels = {0.0}
    for b in boxes:
        if b.rotated:
            continue
        sx, sy, sz = b.part.size
        if sz <= min(sx, sy) and b.part.size[axis] >= 0.4 * extent:
            levels.add(round(b.part.at[2] + sz))
    top = round(max(b.bounds()[1][2] for b in boxes))
    # Keep floor and top; drop levels closer than 60 mm to their neighbours (unreadable text).
    merged = [0.0]
    for level in sorted(levels - {0.0}):
        if level - merged[-1] >= 60 and top - level >= 60:
            merged.append(level)
    merged.append(top)
    return merged


def _fmt(mm: float) -> str:
    return f"{round(mm)}"


def build_view(
    view: View,
    object_type: str,
    boxes: list[Box],
    numbers: list[int],
    names: list[str],
    solids: list[Solid],
    legend: dict[str, str],
) -> Drawing:
    prims: list[Primitive] = []
    largest: dict[int, tuple[float, float, tuple[float, float]]] = {}
    xs: list[float] = []
    ys: list[float] = []
    for i in _paint_order(boxes, view):
        tone = solids[i].tone
        for normal, corners in boxes[i].faces():
            if _dot(normal, view.camera) <= 1e-6:
                continue
            pts = [_project(p, view) for p in corners]
            if _area(pts) < 0.5:
                continue
            prims.append(Polygon(points=pts, tone=tone, shade=_shade(normal)))
            xs += [p[0] for p in pts]
            ys += [p[1] for p in pts]
            area = _area(pts)
            depth = _dot(boxes[i].center(), view.camera)
            best = largest.get(numbers[i])
            if best is None or (depth, area) > (best[0], best[1]):
                largest[numbers[i]] = (depth, area, _centroid(pts))

    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    width, height = max_x - min_x, max_y - min_y
    size = max(width, height, 1.0)
    offset = 0.08 * size
    pad_left = pad_right = pad_top = pad_bottom = 0.05 * size

    if view.dims is not None:
        h_axis, v_axis = (_AXIS[a] for a in view.dims)
        lo = [min(b.bounds()[0][k] for b in boxes) for k in range(3)]
        hi = [max(b.bounds()[1][k] for b in boxes) for k in range(3)]
        prims.append(
            Dimension(
                x1=min_x,
                y1=max_y,
                x2=max_x,
                y2=max_y,
                offset=offset,
                text=_fmt(hi[h_axis] - lo[h_axis]),
            )
        )
        prims.append(
            Dimension(
                x1=min_x,
                y1=min_y,
                x2=min_x,
                y2=max_y,
                offset=-offset,
                text=_fmt(hi[v_axis] - lo[v_axis]),
            )
        )
        pad_bottom = pad_left = offset + 0.07 * size
        if view.chain is not None:
            axis = _AXIS[view.chain]
            levels = _levels(boxes, axis, hi[axis] - lo[axis])
            if 3 <= len(levels) <= 14:
                for z1, z2 in pairwise(levels):
                    prims.append(
                        Dimension(
                            x1=max_x,
                            y1=-z2,
                            x2=max_x,
                            y2=-z1,
                            offset=offset,
                            text=_fmt(z2 - z1),
                        )
                    )
                pad_right = offset + 0.07 * size

    if view.key.startswith("iso") and largest:
        gap = 0.07 * size
        mid = (min_x + max_x) / 2
        spacing = 0.055 * size
        columns: dict[bool, list[tuple[float, int, tuple[float, float]]]] = {True: [], False: []}
        for number, (_, _, target) in sorted(largest.items()):
            columns[target[0] < mid].append((target[1], number, target))
        for left, entries in columns.items():
            entries.sort()
            bx = min_x - gap if left else max_x + gap
            placed: list[float] = []
            for ty, _, _ in entries:
                y = max(ty, placed[-1] + spacing) if placed else ty
                placed.append(y)
            overflow = (placed[-1] - max_y) if placed else 0
            if overflow > 0:
                placed = [max(y - overflow, min_y + k * spacing) for k, y in enumerate(placed)]
            for (_, number, target), by in zip(entries, placed, strict=True):
                prims.append(
                    Callout(
                        x=target[0], y=target[1], bx=round(bx, 2), by=round(by, 2), text=str(number)
                    )
                )
                min_y, max_y = min(min_y, by - spacing / 2), max(max_y, by + spacing / 2)
        pad_left = pad_right = gap + 0.05 * size

    lo3 = [min(b.bounds()[0][k] for b in boxes) for k in range(3)]
    hi3 = [max(b.bounds()[1][k] for b in boxes) for k in range(3)]
    dims_text = " × ".join(_fmt(hi3[k] - lo3[k]) for k in range(3))
    positions = len(set(numbers))
    return Drawing(
        view=view.key,
        title=view.title,
        description=(
            f"{view.title} von {object_type} ({dims_text} mm, B × T × H) mit {positions} "
            f"Positionen: " + ", ".join(f"{n} {names[n - 1]}" for n in sorted(set(numbers)))
        ),
        scale_hint="nicht maßstäblich",
        min_x=round(min_x - pad_left, 2),
        min_y=round(min_y - pad_top, 2),
        width=round(width + pad_left + pad_right, 2),
        height=round(max_y - min_y + pad_top + pad_bottom, 2),
        primitives=prims,
        legend=[LegendEntry(tone=t, label=label) for t, label in sorted(legend.items())],
    )


def build_drawings(
    object_type: str,
    boxes: list[Box],
    numbers: list[int],
    names: list[str],
    solids: list[Solid],
    legend: dict[str, str],
    wall_side: bool = False,
) -> list[Drawing]:
    views = (*VIEWS, *WALL_SIDE_VIEWS) if wall_side else VIEWS
    return [build_view(v, object_type, boxes, numbers, names, solids, legend) for v in views]
