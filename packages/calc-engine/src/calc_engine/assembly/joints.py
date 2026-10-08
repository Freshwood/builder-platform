"""Carpentry joints (tenon, half lap, seat notch) derived from declared part pairs.

The design only names which parts are joined how; the engine finds the touching or overlapping
instances, sizes tenons, laps and notches from the actual geometry and adds the extra stock
length, pegs and timber screws.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from calc_engine.assembly.check import CheckedDesign, notch_depth
from calc_engine.assembly.geometry import Box
from calc_engine.assembly.solid import cross, dot, norm, unit
from construction_model.assembly import AssemblyDesign

TENON_MIN_MM = 30
TENON_MAX_MM = 60
PEG_WIDTH_MM = 200
"""Members at least this wide get two pegs per tenon."""


@dataclass(frozen=True)
class JointWork:
    kind: str
    part: int
    into: int
    text: str
    """What to cut, e.g. 'Zapfen 55 × 120 mm, 60 mm lang'."""
    pegs: int = 0
    screws: int = 0


@dataclass
class JointPlan:
    works: list[JointWork] = field(default_factory=list)
    extra_mm: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    """Additional stock length per part (tenons)."""
    pairs: set[frozenset[int]] = field(default_factory=set)
    """Part pairs joined by carpentry (no automatic screws there)."""

    @property
    def pegs(self) -> int:
        return sum(w.pegs for w in self.works)

    @property
    def screws(self) -> int:
        return sum(w.screws for w in self.works)


def _round5(value: float) -> int:
    return int(5 * round(value / 5))


def _extent(box: Box, direction: tuple[float, float, float]) -> float:
    values = [dot(p, direction) for piece in box.pieces for p in piece.vertices]
    return max(values) - min(values)


def _box_distance(p: tuple[float, float, float], box: Box) -> float:
    lo, hi = box.bounds()
    return math.sqrt(sum(max(lo[k] - p[k], 0.0, p[k] - hi[k]) ** 2 for k in range(3)))


def _nearer_end(part: Box, into: Box) -> str:
    """Which end of ``part`` meets ``into`` (by distance of the end points to its box)."""
    if part.part.start is not None and part.part.end is not None:
        a, b = part.part.start, part.part.end
    else:
        d = part.length_dir()
        c = part.center()
        half = max(part.lu, part.lv) / 2
        a = (c[0] - d[0] * half, c[1] - d[1] * half, c[2] - d[2] * half)
        b = (c[0] + d[0] * half, c[1] + d[1] * half, c[2] + d[2] * half)
    return "Anfang" if _box_distance(a, into) <= _box_distance(b, into) else "Ende"


def plan_joints(design: AssemblyDesign, checked: CheckedDesign) -> JointPlan:
    plan = JointPlan()
    if not design.joints:
        return plan
    boxes = checked.boxes
    kinds = {frozenset((j.part, j.into)): j for j in design.joints}
    overlap_points = {frozenset((o.a, o.b)): o.points for o in checked.overlaps}
    tenon_ends: dict[int, set[str]] = defaultdict(set)
    for contact in checked.contacts:
        a, b = boxes[contact.a], boxes[contact.b]
        joint = kinds.get(frozenset((a.part.spec_id, b.part.spec_id)))
        if joint is None:
            continue
        i, j = (contact.a, contact.b) if a.part.spec_id == joint.part else (contact.b, contact.a)
        if joint.part == joint.into:
            i, j = contact.a, contact.b
        plan.pairs.add(frozenset((i, j)))
        part, into = boxes[i], boxes[j]
        t, w, _ = part.dims
        if joint.kind == "tenon":
            d = part.length_dir()
            end = _nearer_end(part, into)
            depth = _extent(into, d)
            length = max(TENON_MIN_MM, min(TENON_MAX_MM, _round5(0.4 * depth)))
            thick = max(15, _round5(t / 3))
            wide = max(40, _round5(w - 40))
            pegs = 2 if w >= PEG_WIDTH_MM else 1
            if end not in tenon_ends[i]:
                tenon_ends[i].add(end)
                plan.extra_mm[i] += length
            plan.works.append(
                JointWork(
                    "tenon",
                    i,
                    j,
                    f"Zapfen {thick} × {wide} mm, {length} mm lang; Zapfenloch "
                    f"{length + 5} mm tief",
                    pegs=pegs,
                )
            )
        elif joint.kind == "half_lap":
            points = overlap_points.get(frozenset((i, j)), [])
            normal = cross(part.length_dir(), into.length_dir())
            if norm(normal) < 0.1:
                normal = part.frame.w
            values = [dot(p, unit(normal)) for p in points] or [0.0, 2 * t]
            depth = _round5((max(values) - min(values)) / 2)
            plan.works.append(
                JointWork("half_lap", i, j, f"Blatt je {depth} mm tief ausklinken", pegs=1)
            )
        else:
            points = overlap_points.get(frozenset((i, j)), [])
            depth = _round5(notch_depth(part, points)) if points else 0
            seat = f"Kerve {depth} mm tief" if depth else "aufliegend"
            plan.works.append(JointWork("notch", i, j, seat, screws=1))
    return plan


def member_angle(box: Box) -> float | None:
    """Inclination of a member against the horizontal in degrees (None for boxes)."""
    if box.axis is None:
        return None
    return math.degrees(math.asin(min(1.0, abs(box.axis[2]))))
