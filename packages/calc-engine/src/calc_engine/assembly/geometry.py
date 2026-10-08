"""Part geometry for resolved parts: solids, faces, bounding boxes, contacts and overlaps.

A part is a prism: a 2D outline (rectangle or engine-generated contour, minus cutouts) in a
local frame, extruded along its thinnest direction and clipped by end cuts. Boxes keep their
exact, cheap code path; every other part is decomposed into convex pieces (``solid.Convex``).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property
from itertools import combinations

from calc_engine.assembly import shapes
from calc_engine.assembly.resolve import ResolvedPart
from calc_engine.assembly.solid import (
    Convex,
    Plane,
    add,
    cross,
    dot,
    extents_on_plane,
    intersection,
    norm,
    penetration,
    scale,
    sub,
    touching,
    unit,
)
from calc_engine.assembly.solid import Vec as Vec

TOUCH_TOL = 1.0
MIN_CONTACT = 3.0
_AXES = ("x", "y", "z")
_UNIT = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
# Cuts flatter than this against the member axis would leave paper-thin, endless ends.
MIN_CUT_SIN = math.sin(math.radians(10))

Face3 = tuple[Vec, list[Vec], list[list[Vec]]]
"""Display face: outward normal, outer ring, holes."""


class GeometryError(ValueError):
    pass


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


def outline_of(part: ResolvedPart, lu: float, lv: float) -> tuple[shapes.Ring, list[shapes.Ring]]:
    """Outline and holes of a part in its face plane (u, v)."""
    shape = part.shape
    kind = shape.kind if shape else "rect"
    match kind:
        case "rect":
            outer = shapes.rect(lu, lv)
        case "rounded":
            assert shape is not None
            radius = shape.radius if shape.radius is not None else 0.15 * min(lu, lv)
            outer = shapes.rounded(lu, lv, radius)
        case "ellipse":
            outer = shapes.ellipse(lu, lv)
        case "triangle":
            assert shape is not None
            outer = shapes.triangle(lu, lv, shape.apex)
        case "arch":
            outer = shapes.arch(lu, lv)
        case "cloud":
            assert shape is not None
            outer = shapes.cloud(lu, lv, shape.bumps)
        case _:
            assert shape is not None
            outer = shapes.polygon(shape.points)
            x0, y0, x1, y1 = shapes.bbox(outer)
            if x0 < -0.5 or y0 < -0.5 or x1 > lu + 0.5 or y1 > lv + 0.5:
                raise GeometryError(
                    f"Polygon-Punkte müssen in 0–{lu:g} × 0–{lv:g} mm (u × v) liegen"
                )
    holes: list[shapes.Ring] = []
    for c in part.cutouts:
        if c.kind == "polygon":
            ring = shapes.polygon(c.points)
        elif min(c.size) <= 0:
            raise GeometryError("Ausschnitt braucht eine Größe > 0")
        elif c.kind == "ellipse":
            ring = shapes.ellipse(c.size[0], c.size[1], c.at[0], c.at[1])
        else:
            ring = shapes.rect(c.size[0], c.size[1], c.at[0], c.at[1])
        holes.append(shapes.oriented(ring, ccw=False))
    errors = shapes.check_holes(outer, holes)
    if errors:
        raise GeometryError("; ".join(errors))
    return shapes.oriented(outer, ccw=True), holes


@dataclass(frozen=True)
class Frame:
    origin: Vec
    u: Vec
    v: Vec
    w: Vec

    def point(self, u: float, v: float, w: float) -> Vec:
        return add(self.origin, add(scale(self.u, u), add(scale(self.v, v), scale(self.w, w))))


class Box:
    """A part as a solid in world coordinates (the name stems from the box-only engine)."""

    def __init__(self, part: ResolvedPart, section: tuple[float, float] | None = None) -> None:
        self.part = part
        self.planes: list[Plane] = []
        self.axis: Vec | None = None
        if part.is_member:
            if section is None:
                raise GeometryError("Stab braucht einen Querschnitt (section oder Material)")
            self._member(section)
        else:
            self._box()
        self.outline, self.holes = outline_of(part, self.lu, self.lv)
        self.aligned = (
            not part.is_member
            and part.rotation is None
            and (part.shape is None or part.shape.kind == "rect")
            and not part.cutouts
        )

    # --- Construction ------------------------------------------------------------------------

    def _box(self) -> None:
        size = self.part.size
        k = min(range(3), key=lambda i: (size[i], -i))
        a, b = (i for i in range(3) if i != k)
        u, v, w = _UNIT[a], _UNIT[b], _UNIT[k]
        if self.part.rotation is not None:
            u, v, w = (_rotate_dir(d, *self.part.rotation) for d in (u, v, w))
        self.frame = Frame(self.part.at, u, v, w)
        self.lu, self.lv, self.lw = size[a], size[b], size[k]

    def _member(self, section: tuple[float, float]) -> None:
        part = self.part
        assert part.start is not None
        assert part.end is not None
        a, b = part.start, part.end
        length = norm(sub(b, a))
        if length < 20:
            raise GeometryError("start und end liegen weniger als 20 mm auseinander")
        d = unit(sub(b, a))
        t, w = sorted(section)
        if t <= 0:
            raise GeometryError("Querschnitt muss größer 0 sein")
        thick = self._thickness_dir(d)
        width = cross(d, thick)
        back = scale(d, -1.0)
        start_planes = self._cut_planes(part.cuts[0], a, d)
        end_planes = self._cut_planes(part.cuts[1], b, back)
        if start_planes or end_planes:
            # The prism is extended for angled cuts, so square ends need their plane, too.
            start_planes = start_planes or [Plane(back, -dot(d, a))]
            end_planes = end_planes or [Plane(d, dot(d, b))]
        cut_planes = [*start_planes, *end_planes]
        if part.shape is not None and cut_planes:
            raise GeometryError("Form und Schrägschnitt lassen sich nicht kombinieren")
        ext = 0.0
        if cut_planes:
            s_min = min(abs(dot(p.normal, d)) for p in cut_planes)
            ext = (t + w) / s_min + 1.0
        self.planes = cut_planes
        self.axis = d
        origin = sub(sub(sub(a, scale(d, ext)), scale(width, w / 2)), scale(thick, t / 2))
        self.frame = Frame(origin, d, width, thick)
        self.lu, self.lv, self.lw = length + 2 * ext, w, t

    def _thickness_dir(self, d: Vec) -> Vec:
        if self.part.facing is not None:
            f = _UNIT[_AXES.index(self.part.facing)]
            t = sub(f, scale(d, dot(f, d)))
            if norm(t) < 0.2:
                raise GeometryError(f"facing '{self.part.facing}' verläuft entlang des Stabs")
            return unit(t)
        c = cross((0.0, 0.0, 1.0), d)
        if norm(c) > 0.2:
            return unit(c)
        # Vertical members: thickness across the front view (y), like posts in a wall along x.
        return unit(sub((0.0, 1.0, 0.0), scale(d, d[1])))

    @staticmethod
    def _cut_planes(kind: str, at: Vec, d: Vec) -> list[Plane]:
        """Planes that keep the member's side (direction ``d``) of the end point ``at``."""
        dirs: list[Vec] = []
        for k in ("level", "plumb") if kind == "corner" else (kind,):
            if k == "square":
                continue
            if k == "level":
                if abs(d[2]) < MIN_CUT_SIN:
                    raise GeometryError("Waagschnitt (level) braucht ein geneigtes Bauteil")
                dirs.append((0.0, 0.0, math.copysign(1.0, d[2])))
            else:
                horizontal = (d[0], d[1], 0.0)
                if norm(horizontal) < MIN_CUT_SIN:
                    raise GeometryError("Lotschnitt (plumb) braucht ein geneigtes Bauteil")
                dirs.append(unit(horizontal))
        return [Plane(scale(n, -1.0), -dot(n, at)) for n in dirs]

    # --- Properties --------------------------------------------------------------------------

    @property
    def rotated(self) -> bool:
        """True if the part is not an axis-aligned plain box (exact box shortcuts do not apply)."""
        return not self.aligned

    @cached_property
    def pieces(self) -> list[Convex]:
        boundary = shapes.boundary_edges(self.outline, self.holes)
        out: list[Convex] = []
        for ring in shapes.convex_pieces(self.outline, self.holes):
            polys: list[tuple[list[Vec], bool]] = [
                ([self.frame.point(u, v, 0.0) for u, v in ring], True),
                ([self.frame.point(u, v, self.lw) for u, v in ring], True),
            ]
            for p, q in zip(ring, [*ring[1:], ring[0]], strict=True):
                edge = (p, q) if p <= q else (q, p)
                polys.append(
                    (
                        [
                            self.frame.point(*p, 0.0),
                            self.frame.point(*q, 0.0),
                            self.frame.point(*q, self.lw),
                            self.frame.point(*p, self.lw),
                        ],
                        edge in boundary,
                    )
                )
            piece: Convex | None = Convex.from_faces(polys)
            for plane in self.planes:
                if piece is None:
                    break
                piece = piece.clip(plane)
            if piece is not None:
                out.append(piece)
        if not out:
            raise GeometryError("Die Schnitte lassen vom Bauteil nichts übrig")
        return out

    def corners(self) -> list[Vec]:
        if self.aligned:
            (ax, ay, az), (sx, sy, sz) = self.part.at, self.part.size
            return [
                (ax + dx * sx, ay + dy * sy, az + dz * sz)
                for dz in (0, 1)
                for dy in (0, 1)
                for dx in (0, 1)
            ]
        return [p for _, ring, holes in self.faces() for r in (ring, *holes) for p in r]

    def faces(self) -> list[Face3]:
        """Visible faces for drawings and meshes (outer ring, holes; outward normal)."""
        return self._faces

    @cached_property
    def _faces(self) -> list[Face3]:
        if self.aligned:
            c = self.corners()
            quads = [
                ((-1.0, 0.0, 0.0), [0, 2, 6, 4]),
                ((1.0, 0.0, 0.0), [1, 5, 7, 3]),
                ((0.0, -1.0, 0.0), [0, 4, 5, 1]),
                ((0.0, 1.0, 0.0), [2, 3, 7, 6]),
                ((0.0, 0.0, -1.0), [0, 1, 3, 2]),
                ((0.0, 0.0, 1.0), [4, 6, 7, 5]),
            ]
            return [(n, [c[i] for i in idx], []) for n, idx in quads]
        f = self.frame
        faces: list[Face3] = [
            (
                scale(f.w, -1.0),
                [f.point(u, v, 0.0) for u, v in self.outline],
                [[f.point(u, v, 0.0) for u, v in h] for h in self.holes],
            ),
            (
                f.w,
                [f.point(u, v, self.lw) for u, v in self.outline],
                [[f.point(u, v, self.lw) for u, v in h] for h in self.holes],
            ),
        ]
        for ring2d in (self.outline, *self.holes):
            for (u1, v1), (u2, v2) in zip(ring2d, [*ring2d[1:], ring2d[0]], strict=True):
                du, dv = u2 - u1, v2 - v1
                length = math.hypot(du, dv)
                if length < 1e-6:
                    continue
                normal = unit(sub(scale(f.u, dv), scale(f.v, du)))
                quad = [
                    f.point(u1, v1, 0.0),
                    f.point(u2, v2, 0.0),
                    f.point(u2, v2, self.lw),
                    f.point(u1, v1, self.lw),
                ]
                faces.append((normal, quad, []))
        for plane in self.planes:
            clipped: list[Face3] = []
            for normal, ring, holes in faces:
                outer = _clip_ring(ring, plane)
                if len(outer) >= 3:
                    kept = [h for h in (_clip_ring(h, plane) for h in holes) if len(h) >= 3]
                    clipped.append((normal, outer, kept))
            faces = clipped
        for plane in self.planes:
            for piece in self.pieces:
                for face in piece.faces:
                    if dot(face.normal, plane.normal) > 0.9999 and all(
                        abs(plane.distance(p)) < 0.1 for p in face.points
                    ):
                        faces.append((face.normal, list(face.points), []))
        return faces

    def bounds(self) -> tuple[Vec, Vec]:
        return self._bounds

    @cached_property
    def _bounds(self) -> tuple[Vec, Vec]:
        pts = self.corners()
        lo = (min(p[0] for p in pts), min(p[1] for p in pts), min(p[2] for p in pts))
        hi = (max(p[0] for p in pts), max(p[1] for p in pts), max(p[2] for p in pts))
        return lo, hi

    def center(self) -> Vec:
        lo, hi = self.bounds()
        return ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2)

    @property
    def size(self) -> Vec:
        """Extent along x, y, z (boxes: their size; other parts: their bounding box)."""
        if self.aligned:
            return self.part.size
        lo, hi = self.bounds()
        return (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])

    @cached_property
    def volume_mm3(self) -> float:
        if self.aligned:
            sx, sy, sz = self.part.size
            return sx * sy * sz
        return sum(p.volume() for p in self.pieces)

    @cached_property
    def surface_mm2(self) -> float:
        total = 0.0
        for normal, ring, holes in self.faces():
            total += _area3(ring, normal) - sum(_area3(h, normal) for h in holes)
        return total

    @property
    def face_area_mm2(self) -> float:
        """Area of the outline face (minus cutouts), e.g. for infill or roofing per m²."""
        return shapes.area(self.outline, self.holes) if not self.planes else self._clipped_face_area

    @cached_property
    def _clipped_face_area(self) -> float:
        return max(
            (_area3(r, n) - sum(_area3(h, n) for h in hs) for n, r, hs in self.faces()[:2]),
            default=0.0,
        )

    @property
    def dims(self) -> tuple[float, float, float]:
        """(thickness, width, length) of the stock the part is cut from."""
        if self.part.is_member:
            assert self.axis is not None
            pts = [p for piece in self.pieces for p in piece.vertices]
            values = [dot(p, self.axis) for p in pts]
            return (self.lw, self.lv, max(values) - min(values))
        t, w, length = sorted((self.lw, self.lu, self.lv))
        return (t, w, length)

    @property
    def shaped(self) -> bool:
        return self.part.shape is not None and self.part.shape.kind != "rect"

    def length_dir(self) -> Vec:
        if self.axis is not None:
            return self.axis
        return self.frame.u if self.lu >= self.lv else self.frame.v

    def mesh(self) -> tuple[list[Vec], list[tuple[int, int, int]]]:
        """Triangle mesh of the visible faces (counter-clockwise seen from outside)."""
        vertices: list[Vec] = []
        index: dict[tuple[float, float, float], int] = {}
        triangles: list[tuple[int, int, int]] = []

        def vid(p: Vec) -> int:
            key = (round(p[0], 1), round(p[1], 1), round(p[2], 1))
            if key not in index:
                index[key] = len(vertices)
                vertices.append(key)
            return index[key]

        for normal, ring, holes in self.faces():
            u = unit(sub(ring[1], ring[0])) if norm(sub(ring[1], ring[0])) > 1e-9 else None
            if u is None:
                continue
            v = cross(normal, u)
            origin = ring[0]

            def flat(p: Vec, o: Vec = origin, bu: Vec = u, bv: Vec = v) -> shapes.Pt:
                d = sub(p, o)
                return (round(dot(d, bu), 4), round(dot(d, bv), 4))

            lookup = {flat(p): p for r in (ring, *holes) for p in r}
            try:
                tris = shapes.triangulate(
                    [flat(p) for p in ring], [[flat(p) for p in h] for h in holes]
                )
            except shapes.ShapeError:
                continue
            for a, b, c in tris:
                pa, pb, pc = (lookup.get(x) or _unflat(x, origin, u, v) for x in (a, b, c))
                if dot(cross(sub(pb, pa), sub(pc, pa)), normal) < 0:
                    pb, pc = pc, pb
                triangles.append((vid(pa), vid(pb), vid(pc)))
        return vertices, triangles


def _unflat(p: shapes.Pt, origin: Vec, u: Vec, v: Vec) -> Vec:
    return add(origin, add(scale(u, p[0]), scale(v, p[1])))


def _clip_ring(ring: list[Vec], plane: Plane) -> list[Vec]:
    out: list[Vec] = []
    for a, b in zip(ring, [*ring[1:], ring[0]], strict=True):
        da, db = plane.distance(a), plane.distance(b)
        if da <= 0:
            out.append(a)
        if (da < 0 < db) or (db < 0 < da):
            t = da / (da - db)
            out.append(add(a, scale(sub(b, a), t)))
    return out


def _area3(ring: list[Vec], normal: Vec) -> float:
    total = (0.0, 0.0, 0.0)
    for a, b in zip(ring, [*ring[1:], ring[0]], strict=True):
        total = add(total, cross(a, b))
    return abs(dot(total, normal)) / 2


@dataclass(frozen=True)
class Contact:
    a: int
    b: int
    axis: int | None
    """Contact normal axis (0=x, 1=y, 2=z) if it is a world axis; None otherwise."""
    extent: tuple[float, float]
    """Size of the contact rectangle (larger first)."""
    normal: Vec | None = None
    """Normal pointing from part a to part b (None for overlapping joints)."""


@dataclass(frozen=True)
class Collision:
    a: int
    b: int
    overlap: Vec


@dataclass(frozen=True)
class Overlap:
    """Allowed interpenetration (declared joint); ``points`` are the intersection's vertices."""

    a: int
    b: int
    points: list[Vec]


def bounds_of(boxes: list[Box]) -> tuple[Vec, Vec]:
    los, his = zip(*(b.bounds() for b in boxes), strict=True)
    lo = (min(p[0] for p in los), min(p[1] for p in los), min(p[2] for p in los))
    hi = (max(p[0] for p in his), max(p[1] for p in his), max(p[2] for p in his))
    return lo, hi


def _axis_of(normal: Vec) -> int | None:
    for k in range(3):
        if abs(normal[k]) > 0.9995:
            return k
    return None


def analyse(
    boxes: list[Box], overlap_ok: Callable[[int, int], bool] | None = None
) -> tuple[list[Contact], list[Collision], list[Overlap]]:
    """Find touching faces, interpenetrations and allowed overlaps between all pairs of parts."""
    allowed = overlap_ok or (lambda _a, _b: False)
    bounds = [b.bounds() for b in boxes]
    contacts: list[Contact] = []
    collisions: list[Collision] = []
    overlaps: list[Overlap] = []
    for i, j in combinations(range(len(boxes)), 2):
        (alo, ahi), (blo, bhi) = bounds[i], bounds[j]
        overlap = tuple(min(ahi[k], bhi[k]) - max(alo[k], blo[k]) for k in range(3))
        if any(o < -TOUCH_TOL for o in overlap):
            continue
        if boxes[i].rotated or boxes[j].rotated:
            _analyse_solids(i, j, boxes, allowed(i, j), contacts, collisions, overlaps)
            continue
        touching_axes = [k for k in range(3) if abs(overlap[k]) <= TOUCH_TOL]
        inside = [k for k in range(3) if overlap[k] > TOUCH_TOL]
        if len(inside) == 3:
            if allowed(i, j):
                lo = tuple(max(alo[k], blo[k]) for k in range(3))
                hi = tuple(min(ahi[k], bhi[k]) for k in range(3))
                pts = [
                    (x, y, z)
                    for x in (lo[0], hi[0])
                    for y in (lo[1], hi[1])
                    for z in (lo[2], hi[2])
                ]
                overlaps.append(Overlap(i, j, pts))
                dims = sorted(overlap, reverse=True)
                contacts.append(Contact(i, j, None, (dims[0], dims[1])))
            else:
                collisions.append(Collision(i, j, (overlap[0], overlap[1], overlap[2])))
        elif len(touching_axes) == 1 and all(overlap[k] >= MIN_CONTACT for k in inside):
            k = touching_axes[0]
            others = sorted((overlap[m] for m in inside), reverse=True)
            sign = 1.0 if boxes[i].center()[k] < boxes[j].center()[k] else -1.0
            normal = tuple(sign if m == k else 0.0 for m in range(3))
            contacts.append(Contact(i, j, k, (others[0], others[1]), normal))  # type: ignore[arg-type]
    return contacts, collisions, overlaps


def _analyse_solids(
    i: int,
    j: int,
    boxes: list[Box],
    allowed: bool,
    contacts: list[Contact],
    collisions: list[Collision],
    overlaps: list[Overlap],
) -> None:
    a, b = boxes[i], boxes[j]
    inter_points: list[Vec] = []
    deepest = 0.0
    for pa in a.pieces:
        for pb in b.pieces:
            depth = penetration(pa, pb)
            if depth > TOUCH_TOL:
                deepest = max(deepest, depth)
                both = intersection(pa, pb)
                if both is not None:
                    inter_points.extend(both.vertices)
    if deepest > TOUCH_TOL and inter_points:
        if allowed:
            overlaps.append(Overlap(i, j, inter_points))
            lo = [min(p[k] for p in inter_points) for k in range(3)]
            hi = [max(p[k] for p in inter_points) for k in range(3)]
            dims = sorted((hi[k] - lo[k] for k in range(3)), reverse=True)
            contacts.append(Contact(i, j, None, (dims[0], dims[1])))
        else:
            lo = [min(p[k] for p in inter_points) for k in range(3)]
            hi = [max(p[k] for p in inter_points) for k in range(3)]
            collisions.append(Collision(i, j, (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])))
        return
    area = 0.0
    points: list[Vec] = []
    normal: Vec | None = None
    for pa in a.pieces:
        for pb in b.pieces:
            for touch in touching(pa, pb, TOUCH_TOL):
                if normal is None:
                    normal = touch.normal
                elif dot(normal, touch.normal) < 0.999:
                    continue
                area += touch.area
                points.extend(touch.points)
    if normal is None or area < MIN_CONTACT * MIN_CONTACT:
        return
    extent = extents_on_plane(points, normal)
    if extent[1] < MIN_CONTACT:
        return
    contacts.append(Contact(i, j, _axis_of(normal), extent, normal))


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
