"""Box geometry for resolved parts: corners, faces, bounding boxes and contacts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations

from calc_engine.assembly.resolve import ResolvedPart

Vec = tuple[float, float, float]

TOUCH_TOL = 1.0
MIN_CONTACT = 3.0
_AXES = ("x", "y", "z")


def _rotate(p: Vec, pivot: Vec, axis: str, deg: float) -> Vec:
    rad = math.radians(deg)
    c, s = math.cos(rad), math.sin(rad)
    x, y, z = p[0] - pivot[0], p[1] - pivot[1], p[2] - pivot[2]
    if axis == "x":
        y, z = y * c - z * s, y * s + z * c
    elif axis == "y":
        x, z = x * c + z * s, -x * s + z * c
    else:
        x, y = x * c - y * s, x * s + y * c
    return (x + pivot[0], y + pivot[1], z + pivot[2])


def _rotate_dir(v: Vec, axis: str, deg: float) -> Vec:
    return _rotate(v, (0.0, 0.0, 0.0), axis, deg)


@dataclass(frozen=True)
class Box:
    """A part as an (optionally rotated) box in world coordinates."""

    part: ResolvedPart

    @property
    def rotated(self) -> bool:
        return self.part.rotation is not None

    def corners(self) -> list[Vec]:
        (ax, ay, az), (sx, sy, sz) = self.part.at, self.part.size
        pts = [
            (ax + dx * sx, ay + dy * sy, az + dz * sz)
            for dz in (0, 1)
            for dy in (0, 1)
            for dx in (0, 1)
        ]
        if self.part.rotation is None:
            return pts
        axis, deg = self.part.rotation
        return [_rotate(p, self.part.at, axis, deg) for p in pts]

    def faces(self) -> list[tuple[Vec, list[Vec]]]:
        """Six faces as (outward normal, 4 corners in order)."""
        c = self.corners()
        # Corner index = dx + 2*dy + 4*dz
        quads = [
            ((-1.0, 0.0, 0.0), [0, 2, 6, 4]),
            ((1.0, 0.0, 0.0), [1, 5, 7, 3]),
            ((0.0, -1.0, 0.0), [0, 4, 5, 1]),
            ((0.0, 1.0, 0.0), [2, 3, 7, 6]),
            ((0.0, 0.0, -1.0), [0, 1, 3, 2]),
            ((0.0, 0.0, 1.0), [4, 6, 7, 5]),
        ]
        out: list[tuple[Vec, list[Vec]]] = []
        for normal, idx in quads:
            n = normal
            if self.part.rotation is not None:
                n = _rotate_dir(normal, *self.part.rotation)
            out.append((n, [c[i] for i in idx]))
        return out

    def bounds(self) -> tuple[Vec, Vec]:
        pts = self.corners()
        lo = (min(p[0] for p in pts), min(p[1] for p in pts), min(p[2] for p in pts))
        hi = (max(p[0] for p in pts), max(p[1] for p in pts), max(p[2] for p in pts))
        return lo, hi

    def center(self) -> Vec:
        lo, hi = self.bounds()
        return ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2)

    @property
    def volume_mm3(self) -> float:
        sx, sy, sz = self.part.size
        return sx * sy * sz


@dataclass(frozen=True)
class Contact:
    a: int
    b: int
    axis: int | None
    """Contact normal axis (0=x, 1=y, 2=z) for axis-aligned parts; None if approximated."""
    extent: tuple[float, float]
    """Size of the contact rectangle (larger first)."""


@dataclass(frozen=True)
class Collision:
    a: int
    b: int
    overlap: Vec


def bounds_of(boxes: list[Box]) -> tuple[Vec, Vec]:
    los, his = zip(*(b.bounds() for b in boxes), strict=True)
    lo = (min(p[0] for p in los), min(p[1] for p in los), min(p[2] for p in los))
    hi = (max(p[0] for p in his), max(p[1] for p in his), max(p[2] for p in his))
    return lo, hi


def analyse(boxes: list[Box]) -> tuple[list[Contact], list[Collision]]:
    """Find touching faces and interpenetrations between all pairs of parts."""
    bounds = [b.bounds() for b in boxes]
    contacts: list[Contact] = []
    collisions: list[Collision] = []
    for i, j in combinations(range(len(boxes)), 2):
        (alo, ahi), (blo, bhi) = bounds[i], bounds[j]
        overlap = tuple(min(ahi[k], bhi[k]) - max(alo[k], blo[k]) for k in range(3))
        if any(o < -TOUCH_TOL for o in overlap):
            continue
        if boxes[i].rotated or boxes[j].rotated:
            dims = sorted((max(o, 0.0) for o in overlap), reverse=True)
            contacts.append(Contact(i, j, None, (max(dims[0], 40.0), max(dims[1], 20.0))))
            continue
        touching = [k for k in range(3) if abs(overlap[k]) <= TOUCH_TOL]
        inside = [k for k in range(3) if overlap[k] > TOUCH_TOL]
        if len(inside) == 3:
            collisions.append(Collision(i, j, (overlap[0], overlap[1], overlap[2])))
        elif len(touching) == 1 and all(overlap[k] >= MIN_CONTACT for k in inside):
            others = sorted((overlap[k] for k in inside), reverse=True)
            contacts.append(Contact(i, j, touching[0], (others[0], others[1])))
    return contacts, collisions


def components(count: int, contacts: list[Contact]) -> list[list[int]]:
    """Connected groups of parts (union-find), each sorted, ordered by first part."""
    parent = list(range(count))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for c in contacts:
        ra, rb = find(c.a), find(c.b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    groups: dict[int, list[int]] = {}
    for i in range(count):
        groups.setdefault(find(i), []).append(i)
    return sorted(groups.values(), key=lambda g: g[0])


def axis_name(axis: int) -> str:
    return _AXES[axis]
