"""Two-dimensional outlines of shaped parts: generation, validation and triangulation.

All outlines live in a part's face plane (u, v) in mm, inside the box [0, w] × [0, h]. Outer
rings are counter-clockwise, holes clockwise. The engine generates curved outlines (cloud,
ellipse, arch, rounded corners) itself, so the LLM only names the shape.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

Pt = tuple[float, float]
Ring = list[Pt]

ARC_SEGMENTS = 48
CLOUD_SAMPLES = 96
_EPS = 1e-9


class ShapeError(ValueError):
    pass


def signed_area(ring: Sequence[Pt]) -> float:
    total = 0.0
    for (x1, y1), (x2, y2) in zip(ring, [*ring[1:], ring[0]], strict=True):
        total += x1 * y2 - x2 * y1
    return total / 2


def oriented(ring: Sequence[Pt], ccw: bool) -> Ring:
    out = list(ring)
    if (signed_area(out) > 0) != ccw:
        out.reverse()
    return out


def bbox(ring: Sequence[Pt]) -> tuple[float, float, float, float]:
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def _clean(ring: Sequence[Pt], tol: float = 0.05) -> Ring:
    """Drop duplicate and collinear points (keeps the shape, shortens meshes)."""
    pts: Ring = []
    for p in ring:
        q = (round(p[0], 2), round(p[1], 2))
        if not pts or math.dist(q, pts[-1]) > tol:
            pts.append(q)
    if len(pts) > 1 and math.dist(pts[0], pts[-1]) <= tol:
        pts.pop()
    changed = True
    while changed and len(pts) > 3:
        changed = False
        for i in range(len(pts)):
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
            if abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) <= tol:
                pts.pop(i)
                changed = True
                break
    return pts


def _arc(cx: float, cy: float, rx: float, ry: float, a0: float, a1: float, n: int) -> Ring:
    return [
        (cx + rx * math.cos(a0 + (a1 - a0) * k / n), cy + ry * math.sin(a0 + (a1 - a0) * k / n))
        for k in range(n + 1)
    ]


def rect(w: float, h: float, u: float = 0.0, v: float = 0.0) -> Ring:
    return [(u, v), (u + w, v), (u + w, v + h), (u, v + h)]


def ellipse(w: float, h: float, u: float = 0.0, v: float = 0.0) -> Ring:
    ring = _arc(u + w / 2, v + h / 2, w / 2, h / 2, 0.0, 2 * math.pi, ARC_SEGMENTS)
    return _clean(ring[:-1])


def rounded(w: float, h: float, radius: float) -> Ring:
    r = max(0.0, min(radius, w / 2, h / 2))
    if r < 0.5:
        return rect(w, h)
    q = ARC_SEGMENTS // 4
    ring = (
        _arc(w - r, r, r, r, -math.pi / 2, 0.0, q)
        + _arc(w - r, h - r, r, r, 0.0, math.pi / 2, q)
        + _arc(r, h - r, r, r, math.pi / 2, math.pi, q)
        + _arc(r, r, r, r, math.pi, 1.5 * math.pi, q)
    )
    return _clean(ring)


def triangle(w: float, h: float, apex: float | None) -> Ring:
    a = w / 2 if apex is None else apex
    if not -0.5 <= a <= w + 0.5:
        raise ShapeError(f"Spitze bei u = {a:g} mm liegt außerhalb der Breite 0–{w:g} mm")
    return _clean([(0.0, 0.0), (w, 0.0), (a, h)])


def arch(w: float, h: float) -> Ring:
    """Rectangle with a (semi-)elliptic top; the arch rises at most half the width."""
    rise = min(w / 2, h)
    side = h - rise
    top = _arc(w / 2, side, w / 2, rise, 0.0, math.pi, ARC_SEGMENTS // 2)
    return _clean([(0.0, 0.0), (w, 0.0), *top])


def cloud(w: float, h: float, bumps: int | None) -> Ring:
    """A cloud with a flat bottom: round side lobes and a row of bumps, scaled to w × h.

    Built in units of the height (width = aspect) so the bumps stay round, then fitted.
    """
    a = max(w / max(h, 1.0), 0.6)
    k = bumps or max(2, min(7, round(2.2 * a)))
    lobe = min(0.38, a / 4)
    x1, x2 = lobe + 0.08, a - lobe - 0.08
    pitch = (x2 - x1) / (k - 1) if k > 1 else 0.0
    rb = min(0.36, max(0.2, 0.62 * pitch)) if k > 1 else min(0.36, a / 3)
    circles = [(lobe, lobe, lobe), (a - lobe, lobe, lobe)]
    for i in range(k):
        t = (i + 0.5) / k
        cx = x1 + i * pitch if k > 1 else a / 2
        circles.append((cx, 1 - rb - 0.1 * (1 - math.sin(math.pi * t)), rb))
    base = (lobe, a - lobe, 1 - rb - 0.1)

    def column(x: float) -> tuple[float, float] | None:
        tops: list[float] = []
        bottoms: list[float] = []
        for cx, cy, r in circles:
            if abs(x - cx) < r:
                dy = math.sqrt(r * r - (x - cx) ** 2)
                tops.append(cy + dy)
                bottoms.append(cy - dy)
        if base[0] <= x <= base[1]:
            tops.append(base[2])
            bottoms.append(0.0)
        if not tops:
            return None
        return max(0.0, min(bottoms)), max(tops)

    lo_x = min(cx - r for cx, _, r in circles)
    hi_x = max(cx + r for cx, _, r in circles)
    xs = [lo_x + (hi_x - lo_x) * j / CLOUD_SAMPLES for j in range(CLOUD_SAMPLES + 1)]
    xs[0] += 1e-6
    xs[-1] -= 1e-6
    top: Ring = []
    bottom: Ring = []
    for x in xs:
        col = column(x)
        if col is None:
            continue
        bottom.append((x, col[0]))
        top.append((x, col[1]))
    ring = bottom + top[::-1]
    x0, y0, x1b, y1 = bbox(ring)
    scaled = [((x - x0) / (x1b - x0) * w, (y - y0) / (y1 - y0) * h) for x, y in ring]
    return _clean(oriented(scaled, ccw=True))


def polygon(points: Sequence[Pt]) -> Ring:
    ring = _clean(points)
    if len(ring) < 3 or abs(signed_area(ring)) < 1.0:
        raise ShapeError("Polygon braucht mindestens 3 Punkte und eine Fläche")
    if _self_intersects(ring):
        raise ShapeError("Polygon schneidet sich selbst – Punkte in Umlaufreihenfolge angeben")
    return ring


def _cross(o: Pt, a: Pt, b: Pt) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _segments_cross(p1: Pt, p2: Pt, q1: Pt, q2: Pt) -> bool:
    """Proper intersection of two segments (touching endpoints do not count)."""
    d1, d2 = _cross(q1, q2, p1), _cross(q1, q2, p2)
    d3, d4 = _cross(p1, p2, q1), _cross(p1, p2, q2)
    return (d1 * d2 < -_EPS) and (d3 * d4 < -_EPS)


def _edges(ring: Sequence[Pt]) -> list[tuple[Pt, Pt]]:
    return list(zip(ring, [*ring[1:], ring[0]], strict=True))


def _self_intersects(ring: Sequence[Pt]) -> bool:
    edges = _edges(ring)
    n = len(edges)
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            if _segments_cross(*edges[i], *edges[j]):
                return True
    return False


def contains(ring: Sequence[Pt], p: Pt) -> bool:
    """Point strictly inside a ring (even-odd rule)."""
    inside = False
    x, y = p
    for (x1, y1), (x2, y2) in _edges(ring):
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if xi > x:
                inside = not inside
    return inside


def rings_overlap(a: Sequence[Pt], b: Sequence[Pt]) -> bool:
    if any(_segments_cross(*e, *f) for e in _edges(a) for f in _edges(b)):
        return True
    return contains(a, b[0]) or contains(b, a[0])


def check_holes(outer: Ring, holes: list[Ring]) -> list[str]:
    errors: list[str] = []
    for k, hole in enumerate(holes, start=1):
        if not all(contains(outer, p) for p in hole) or any(
            _segments_cross(*e, *f) for e in _edges(outer) for f in _edges(hole)
        ):
            errors.append(f"Ausschnitt {k} liegt nicht vollständig innerhalb der Kontur")
        for m, other in enumerate(holes[: k - 1], start=1):
            if rings_overlap(hole, other):
                errors.append(f"Ausschnitte {m} und {k} überschneiden sich")
    return errors


def area(outer: Ring, holes: Sequence[Ring] = ()) -> float:
    return abs(signed_area(outer)) - sum(abs(signed_area(h)) for h in holes)


def is_convex(ring: Sequence[Pt]) -> bool:
    signs = {
        _cross(ring[i - 2], ring[i - 1], ring[i]) > 0
        for i in range(len(ring))
        if abs(_cross(ring[i - 2], ring[i - 1], ring[i])) > _EPS
    }
    return len(signs) <= 1


# --- Triangulation (ear clipping with hole bridges) ----------------------------------------


def _bridge(outer: Ring, hole: Ring) -> Ring:
    """Join a clockwise hole into the counter-clockwise outer ring by a two-way bridge."""
    m_idx = max(range(len(hole)), key=lambda i: (hole[i][0], -hole[i][1]))
    m = hole[m_idx]
    best: tuple[float, int] | None = None
    for i, (a, b) in enumerate(_edges(outer)):
        if (a[1] - m[1]) * (b[1] - m[1]) > 0 or a[1] == b[1]:
            continue
        x = a[0] + (m[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
        if x < m[0] - _EPS:
            continue
        j = i if a[0] > b[0] else (i + 1) % len(outer)
        if best is None or x < best[0]:
            best = (x, j)
    if best is None:
        raise ShapeError("Ausschnitt liegt außerhalb der Kontur")
    x_hit, p_idx = best
    p = outer[p_idx]
    # A reflex vertex inside the triangle (m, hit, p) would block the bridge: take the one with
    # the smallest angle to the ray instead.
    hit = (x_hit, m[1])
    candidates = []
    for i, q in enumerate(outer):
        if i == p_idx or q[0] < m[0]:
            continue
        prev, nxt = outer[i - 1], outer[(i + 1) % len(outer)]
        if _cross(prev, q, nxt) >= 0:
            continue
        tri = [m, hit, p] if _cross(m, hit, p) > 0 else [m, p, hit]
        if all(_cross(tri[k], tri[(k + 1) % 3], q) > -_EPS for k in range(3)):
            angle = abs(math.atan2(q[1] - m[1], q[0] - m[0]))
            candidates.append((angle, math.dist(m, q), i))
    if candidates:
        p_idx = min(candidates)[2]
    ring = hole[m_idx:] + hole[: m_idx + 1]
    return outer[: p_idx + 1] + ring + outer[p_idx:]


def _is_ear(ring: Ring, i: int) -> bool:
    a, b, c = ring[i - 1], ring[i], ring[(i + 1) % len(ring)]
    if _cross(a, b, c) <= _EPS:
        return False
    for k, p in enumerate(ring):
        if k in {(i - 1) % len(ring), i, (i + 1) % len(ring)}:
            continue
        if p in (a, b, c):
            continue
        if _cross(a, b, p) >= -_EPS and _cross(b, c, p) >= -_EPS and _cross(c, a, p) >= -_EPS:
            return False
    return True


def triangulate(outer: Ring, holes: Sequence[Ring] = ()) -> list[tuple[Pt, Pt, Pt]]:
    """Triangles covering the ring minus its holes (deterministic ear clipping)."""
    ring = oriented(outer, ccw=True)
    for hole in sorted(
        (oriented(h, ccw=False) for h in holes), key=lambda h: -max(p[0] for p in h)
    ):
        ring = _bridge(ring, hole)
    if not holes and is_convex(ring):
        return [(ring[0], ring[i], ring[i + 1]) for i in range(1, len(ring) - 1)]
    tris: list[tuple[Pt, Pt, Pt]] = []
    pts = list(ring)
    guard = 0
    while len(pts) > 3:
        guard += 1
        if guard > 20 * len(ring) + 100:
            raise ShapeError("Kontur lässt sich nicht zerlegen – einfachere Form wählen")
        for i in range(len(pts)):
            if _is_ear(pts, i):
                tris.append((pts[i - 1], pts[i], pts[(i + 1) % len(pts)]))
                pts.pop(i)
                break
        else:
            # Degenerate remainder (collinear bridge points): drop the flattest vertex.
            flat = min(
                range(len(pts)),
                key=lambda i: abs(_cross(pts[i - 1], pts[i], pts[(i + 1) % len(pts)])),
            )
            pts.pop(flat)
    if abs(_cross(*pts)) > _EPS:
        tris.append((pts[0], pts[1], pts[2]))
    return tris


def convex_pieces(outer: Ring, holes: Sequence[Ring] = ()) -> list[Ring]:
    """Convex pieces covering the shape: the outline itself if possible, else triangles."""
    if not holes and is_convex(outer):
        return [oriented(outer, ccw=True)]
    return [oriented(list(t), ccw=True) for t in triangulate(outer, holes)]


def boundary_edges(outer: Ring, holes: Sequence[Ring] = ()) -> set[tuple[Pt, Pt]]:
    """Undirected boundary edges (to tell outer faces of convex pieces from inner seams)."""
    edges: set[tuple[Pt, Pt]] = set()
    for ring in (outer, *holes):
        for a, b in _edges(ring):
            edges.add((a, b) if a <= b else (b, a))
    return edges
