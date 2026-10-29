"""Convex polyhedra: clipping, separation (SAT), intersection and touching faces.

Every part is decomposed into convex pieces (prisms over convex parts of its outline, clipped by
its end cuts). These pieces answer the engine's geometric questions exactly: do two parts
penetrate, how deep, and which faces touch with what area.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

Vec = tuple[float, float, float]

_EPS = 1e-7
PLANE_TOL = 0.05


def add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a: Vec) -> float:
    return math.sqrt(dot(a, a))


def unit(a: Vec) -> Vec:
    n = norm(a)
    return (a[0] / n, a[1] / n, a[2] / n)


def centroid(points: Sequence[Vec]) -> Vec:
    n = len(points)
    return (
        sum(p[0] for p in points) / n,
        sum(p[1] for p in points) / n,
        sum(p[2] for p in points) / n,
    )


@dataclass(frozen=True)
class Plane:
    """Half-space ``dot(normal, p) <= offset``; ``normal`` is the outward unit normal."""

    normal: Vec
    offset: float

    def distance(self, p: Vec) -> float:
        return dot(self.normal, p) - self.offset


@dataclass(frozen=True)
class Face:
    points: tuple[Vec, ...]
    normal: Vec
    outer: bool
    """False for seams between pieces of the same part (never touch other parts)."""


def _face_normal(points: Sequence[Vec]) -> Vec:
    # Newell's method: robust for slightly non-planar or collinear-start polygons.
    nx = ny = nz = 0.0
    for a, b in zip(points, [*points[1:], points[0]], strict=True):
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return unit((nx, ny, nz))


class Convex:
    """A convex polyhedron given by its faces (outward normals)."""

    def __init__(self, faces: list[Face]) -> None:
        self.faces = faces
        pts: list[Vec] = []
        seen: set[tuple[float, float, float]] = set()
        for f in faces:
            for p in f.points:
                key = (round(p[0], 4), round(p[1], 4), round(p[2], 4))
                if key not in seen:
                    seen.add(key)
                    pts.append(p)
        self.vertices = pts
        xs, ys, zs = zip(*pts, strict=True)
        self.lo: Vec = (min(xs), min(ys), min(zs))
        self.hi: Vec = (max(xs), max(ys), max(zs))

    @classmethod
    def from_faces(cls, polygons: list[tuple[list[Vec], bool]]) -> Convex:
        """Faces in any winding; normals are oriented away from the centroid."""
        center = centroid([p for poly, _ in polygons for p in poly])
        faces: list[Face] = []
        for poly, outer in polygons:
            if len(poly) < 3:
                continue
            n = _face_normal(poly)
            if dot(n, sub(centroid(poly), center)) < 0:
                n = scale(n, -1.0)
                poly = poly[::-1]
            faces.append(Face(tuple(poly), n, outer))
        return cls(faces)

    def planes(self) -> list[Plane]:
        return [Plane(f.normal, dot(f.normal, f.points[0])) for f in self.faces]

    def edges(self) -> list[Vec]:
        dirs: list[Vec] = []
        for f in self.faces:
            for a, b in zip(f.points, [*f.points[1:], f.points[0]], strict=True):
                d = sub(b, a)
                if norm(d) > _EPS:
                    dirs.append(unit(d))
        return dirs

    def volume(self) -> float:
        # Divergence theorem over a fan triangulation of every face.
        total = 0.0
        for f in self.faces:
            a = f.points[0]
            for b, c in zip(f.points[1:-1], f.points[2:], strict=True):
                total += dot(a, cross(b, c))
        return abs(total) / 6

    def clip(self, plane: Plane, cap_outer: bool = True) -> Convex | None:
        """Keep the part inside the half-space; the new cap face is flagged ``cap_outer``."""
        dists = [plane.distance(p) for p in self.vertices]
        if max(dists) <= PLANE_TOL:
            return self
        if min(dists) >= -PLANE_TOL:
            return None
        polys: list[tuple[list[Vec], bool]] = []
        cut: list[Vec] = []
        for f in self.faces:
            kept = _clip_polygon(list(f.points), plane, cut)
            if len(kept) >= 3:
                polys.append((kept, f.outer))
        cap = _convex_hull_on_plane(cut, plane.normal)
        if len(cap) >= 3:
            polys.append((cap, cap_outer))
        if len(polys) < 4:
            return None
        return Convex.from_faces(polys)


def _clip_polygon(poly: list[Vec], plane: Plane, cut: list[Vec]) -> list[Vec]:
    out: list[Vec] = []
    for a, b in zip(poly, [*poly[1:], poly[0]], strict=True):
        da, db = plane.distance(a), plane.distance(b)
        if da <= PLANE_TOL:
            out.append(a)
            if abs(da) <= PLANE_TOL:
                cut.append(a)
        if (da < -PLANE_TOL and db > PLANE_TOL) or (da > PLANE_TOL and db < -PLANE_TOL):
            t = da / (da - db)
            p = add(a, scale(sub(b, a), t))
            out.append(p)
            cut.append(p)
    return out


def _plane_basis(normal: Vec) -> tuple[Vec, Vec]:
    helper = (1.0, 0.0, 0.0) if abs(normal[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = unit(cross(normal, helper))
    return u, cross(normal, u)


def _convex_hull_on_plane(points: list[Vec], normal: Vec) -> list[Vec]:
    if len(points) < 3:
        return []
    u, v = _plane_basis(normal)
    unique: dict[tuple[float, float], Vec] = {}
    for p in points:
        unique.setdefault((round(dot(p, u), 3), round(dot(p, v), 3)), p)
    keys = sorted(unique)
    if len(keys) < 3:
        return []

    def turn(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for k in keys:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], k) <= 1e-6:
            lower.pop()
        lower.append(k)
    upper: list[tuple[float, float]] = []
    for k in reversed(keys):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], k) <= 1e-6:
            upper.pop()
        upper.append(k)
    return [unique[k] for k in lower[:-1] + upper[:-1]]


def _interval(points: Sequence[Vec], axis: Vec) -> tuple[float, float]:
    values = [dot(p, axis) for p in points]
    return min(values), max(values)


def penetration(a: Convex, b: Convex) -> float:
    """Smallest overlap along all separating-axis candidates; ≤ 0 means apart or touching."""
    if any(a.hi[k] < b.lo[k] or b.hi[k] < a.lo[k] for k in range(3)):
        return -1.0
    axes: list[Vec] = [f.normal for f in a.faces] + [f.normal for f in b.faces]
    ea, eb = _unique_dirs(a.edges()), _unique_dirs(b.edges())
    for da in ea:
        for db in eb:
            c = cross(da, db)
            if norm(c) > 1e-6:
                axes.append(unit(c))
    depth = math.inf
    for axis in _unique_dirs(axes):
        lo_a, hi_a = _interval(a.vertices, axis)
        lo_b, hi_b = _interval(b.vertices, axis)
        overlap = min(hi_a, hi_b) - max(lo_a, lo_b)
        if overlap <= 0:
            return overlap
        depth = min(depth, overlap)
    return depth


def separating_axis(a: Convex, b: Convex) -> Vec | None:
    """An axis along which ``a`` lies entirely before ``b`` (pointing from a to b), if any."""
    axes: list[Vec] = [f.normal for f in a.faces] + [f.normal for f in b.faces]
    for da in _unique_dirs(a.edges()):
        for db in _unique_dirs(b.edges()):
            c = cross(da, db)
            if norm(c) > 1e-6:
                axes.append(unit(c))
    for axis in _unique_dirs(axes):
        lo_a, hi_a = _interval(a.vertices, axis)
        lo_b, hi_b = _interval(b.vertices, axis)
        if hi_a <= lo_b + 0.5:
            return axis
        if hi_b <= lo_a + 0.5:
            return scale(axis, -1.0)
    return None


def _unique_dirs(dirs: list[Vec]) -> list[Vec]:
    out: list[Vec] = []
    for d in dirs:
        if not any(abs(abs(dot(d, e)) - 1) < 1e-6 for e in out):
            out.append(d)
    return out


def intersection(a: Convex, b: Convex) -> Convex | None:
    result: Convex | None = a
    for plane in b.planes():
        if result is None:
            return None
        result = result.clip(plane)
    return result


@dataclass(frozen=True)
class Touch:
    """Area-weighted touching between outer faces of two convex pieces."""

    area: float
    normal: Vec
    points: list[Vec]


def touching(a: Convex, b: Convex, tol: float) -> list[Touch]:
    """Outer faces of ``a`` and ``b`` that lie on one plane, facing each other."""
    out: list[Touch] = []
    for fa in a.faces:
        if not fa.outer:
            continue
        for fb in b.faces:
            if not fb.outer or dot(fa.normal, fb.normal) > -0.9995:
                continue
            if abs(dot(fa.normal, sub(fb.points[0], fa.points[0]))) > tol:
                continue
            poly = _overlap_on_plane(list(fa.points), list(fb.points), fa.normal)
            if len(poly) >= 3:
                area = _polygon_area(poly, fa.normal)
                if area > 1.0:
                    out.append(Touch(area, fa.normal, poly))
    return out


def _overlap_on_plane(pa: list[Vec], pb: list[Vec], normal: Vec) -> list[Vec]:
    """Intersection of two convex polygons that lie (nearly) in one plane."""
    origin = pa[0]
    u, v = _plane_basis(normal)

    def flat(p: Vec) -> tuple[float, float]:
        d = sub(p, origin)
        return (dot(d, u), dot(d, v))

    subject = [flat(p) for p in pa]
    clipper = [flat(p) for p in pb]
    if _area2(subject) < 0:
        subject.reverse()
    if _area2(clipper) < 0:
        clipper.reverse()
    for c1, c2 in zip(clipper, [*clipper[1:], clipper[0]], strict=True):
        if not subject:
            break
        inp, subject = subject, []
        for s1, s2 in zip(inp, [*inp[1:], inp[0]], strict=True):
            in1, in2 = _left(c1, c2, s1), _left(c1, c2, s2)
            if in1:
                subject.append(s1)
            if in1 != in2:
                subject.append(_line_hit(c1, c2, s1, s2))
    return [add(origin, add(scale(u, x), scale(v, y))) for x, y in subject]


def _area2(poly: list[tuple[float, float]]) -> float:
    return sum(
        x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(poly, [*poly[1:], poly[0]], strict=True)
    )


def _left(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> bool:
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= -1e-6


def _line_hit(
    a: tuple[float, float], b: tuple[float, float], p: tuple[float, float], q: tuple[float, float]
) -> tuple[float, float]:
    d1 = (b[0] - a[0], b[1] - a[1])
    d2 = (q[0] - p[0], q[1] - p[1])
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < 1e-12:
        return q
    t = ((a[0] - p[0]) * d1[1] - (a[1] - p[1]) * d1[0]) / -den
    return (p[0] + t * d2[0], p[1] + t * d2[1])


def _polygon_area(poly: list[Vec], normal: Vec) -> float:
    total = (0.0, 0.0, 0.0)
    for a, b in zip(poly, [*poly[1:], poly[0]], strict=True):
        total = add(total, cross(a, b))
    return abs(dot(total, normal)) / 2


def extents_on_plane(points: list[Vec], normal: Vec) -> tuple[float, float]:
    """Size of the points' bounding rectangle in the plane, aligned to their longest spread."""
    if len(points) < 2:
        return (0.0, 0.0)
    best: tuple[float, float] = (0.0, 0.0)
    u0, _ = _plane_basis(normal)
    candidates = [u0]
    for a, b in zip(points, [*points[1:], points[0]], strict=True):
        d = sub(b, a)
        d = sub(d, scale(normal, dot(d, normal)))
        if norm(d) > 1.0:
            candidates.append(unit(d))
    for u in candidates:
        v = cross(normal, u)
        lu, hu = _interval(points, u)
        lv, hv = _interval(points, v)
        size = tuple(sorted((hu - lu, hv - lv), reverse=True))
        if best == (0.0, 0.0) or size[0] * size[1] < best[0] * best[1]:
            best = (size[0], size[1])
    return best
