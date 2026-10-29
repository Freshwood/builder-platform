"""Framed wall: plates, posts, braces, openings with door and window, infill or cladding.

Wall frame: u along the wall (0 .. length), v across it (0 .. thickness), z up (0 .. height). The
wall stands on its bottom plate; ``height`` is the top of the top plate. Openings have exactly the
size of the catalog door or window, with a jack post on each side, a header above and (windows) a
sill rail below, so every piece touches its neighbours face to face.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from homeworking.calc_engine.pipeline.blocks.kit import (
    Axes,
    BlockError,
    Ctx,
    Out,
    box,
    long_box,
    member,
)
from homeworking.calc_engine.pipeline.blocks.sym import E, Num, e
from homeworking.construction_model.assembly import Cutout

# (catalog item, width, height, sill height above the top of the bottom plate)
OPENING_SIZES = {
    "door": ("door_wood_1000x2100", 1000, 2100, 0),
    "window": ("window_wood_800x1000", 800, 1000, 900),
    "window_large": ("window_wood_1000x1200", 1000, 1200, 800),
}
PIECE_DEPTH = 78
HEADER_MM = 160  # height of a header; the rest up to the top plate is filled with short posts
RAIL_MM = 100  # sill rail under a window
MIN_GAP_MM = 20
MIN_INFILL_MM = 100  # narrowest Gefach that is filled (the infill materials need 80 mm)
CLADDING = "cladding_larch_24"
CLADDING_MM = 24


@dataclass(frozen=True)
class Style:
    """Cross sections of a wall: a Fachwerk wall has heavy posts, a stud wall slim studs."""

    post: int  # width of a post along the wall
    thickness: int  # wall thickness (v)
    plate: int  # height of the plates
    spacing: int  # largest distance between two posts (centre to centre)
    brace: tuple[int, int]  # brace section (thin, wide); the wide side lies in the wall plane
    infill: str | None  # bulk material between the posts
    cladding: bool  # boards on the outside


FACHWERK = Style(120, 120, 120, 1100, (100, 120), "infill_clay", False)
STUD = Style(60, 120, 60, 625, (60, 120), "insulation_wood_fiber", True)
STYLES = {"fachwerk": FACHWERK, "stud": STUD}


@dataclass(frozen=True)
class Open:
    """An opening on a wall: ``centre`` is its middle along the wall (u)."""

    kind: str
    centre: E


class Wall:
    """Writes the parts of one wall; every position is relative to the wall's lower corner."""

    def __init__(
        self,
        out: Out,
        ax: Axes,
        ctx: Ctx,
        *,
        prefix: str,
        origin: tuple[Num, Num, Num],
        length: Num,
        height: Num,
        style: Style,
        label: str,
    ) -> None:
        self.out, self.ax, self.ctx = out, ax, ctx
        self.prefix, self.label, self.style = prefix, label, style
        self.u0, self.v0, self.z0 = (e(o) for o in origin)
        self.length, self.height = e(length), e(height)
        self.inner = self.height - 2 * style.plate  # between the plates
        self.post_lumber = ctx.lumber(style.post, style.thickness)
        if ctx.num(self.inner) < 1200:
            raise BlockError(f"Wand {label}: Höhe {ctx.num(self.height):.0f} mm ist zu niedrig")

    # --- placing -----------------------------------------------------------------------------

    def box(
        self,
        id: str,
        name: str,
        material: str,
        u: Num,
        z: Num,
        du: Num,
        dz: Num,
        *,
        v: Num = 0,
        dv: Num | None = None,
        count: Num | None = None,
        when: str | None = None,
        cutouts: list[Cutout] | None = None,
    ) -> None:
        box(
            self.out,
            self.ax,
            self.prefix + id,
            name,
            material,
            (self.u0 + u, self.v0 + v, self.z0 + z),
            (du, self.style.thickness if dv is None else dv, dz),
            repeat=None if count is None else (count, "i"),
            when=when,
            cutouts=cutouts,
        )

    def posts(
        self,
        id: str,
        u0: E,
        u1: E,
        z: Num,
        height: Num,
        *,
        name: str = "Pfosten",
        when: str | None = None,
    ) -> tuple[int, E]:
        """Evenly spaced posts from ``u0`` to ``u1``, flush with both ends. Returns the number of
        posts and their pitch (centre to centre)."""
        st = self.style
        span = self.ctx.num(u1 - u0)
        if span < st.post - 0.5:
            return 0, e(0)
        if span < 2 * st.post + 1:
            self.box(id, name, self.post_lumber, u0, z, st.post, height, when=when)
            return 1, e(0)
        bays = max(1, math.ceil((span - st.post) / st.spacing))
        pitch = (u1 - u0 - st.post) / bays
        self.box(
            id,
            name,
            self.post_lumber,
            u0 + pitch * e("i"),
            z,
            st.post,
            height,
            count=bays + 1,
            when=when,
        )
        return bays + 1, pitch

    # --- the wall ----------------------------------------------------------------------------

    def build(self, openings: list[Open], *, braces: bool, outside: int) -> None:
        st, ctx = self.style, self.ctx
        lum_plate = ctx.lumber(st.plate, st.thickness)
        plate = st.plate
        long_box(
            self.out,
            self.ax,
            ctx,
            self.prefix + "sill",
            f"Schwelle {self.label}",
            lum_plate,
            self.u0,
            self.length,
            self.v0,
            self.z0,
            st.thickness,
            plate,
        )
        long_box(
            self.out,
            self.ax,
            ctx,
            self.prefix + "plate",
            f"Rähm {self.label}",
            lum_plate,
            self.u0,
            self.length,
            self.v0,
            self.z0 + self.height - plate,
            st.thickness,
            plate,
        )

        ranges = self._ranges(openings)
        segments: list[tuple[E, E]] = []
        cursor: E = e(0)
        for _, start, end in ranges:
            segments.append((cursor, start))
            cursor = end
        segments.append((cursor, self.length))

        for k, (s0, s1) in enumerate(segments):
            if ctx.num(s1 - s0) < st.post - 0.5:
                continue
            self._segment(k, s0, s1, self._braced(k, segments) if braces else (False, False))
        for j, (item, start, end) in enumerate(ranges):
            self._opening(j, item, start, end)
        if st.cladding:
            self._cladding(ranges, outside)

    def _ranges(self, openings: list[Open]) -> list[tuple[Open, E, E]]:
        ranges: list[tuple[Open, E, E]] = []
        for item in openings:
            width = OPENING_SIZES[item.kind][1]
            start = item.centre - width / 2
            ranges.append((item, start, start + width))
        ranges.sort(key=lambda r: self.ctx.num(r[1]))
        low = 0.0
        for item, start, end in ranges:
            if self.ctx.num(start) < low - 0.5:
                raise BlockError(
                    f"Wand {self.label}: {item.kind} liegt zu nah an der Ecke oder an einer "
                    f"anderen Öffnung (mindestens {self.style.post} mm Pfosten dazwischen)"
                )
            low = self.ctx.num(end) + self.style.post
        if ranges and low > self.ctx.num(self.length) + 0.5:
            raise BlockError(
                f"Wand {self.label}: die letzte Öffnung ragt in die Ecke – Wand verlängern "
                "oder Position ändern"
            )
        return ranges

    # Brace bay: horizontal run of a brace; steeper than 45° so it stays inside one wall height.
    def _bay(self) -> float:
        return round(self.ctx.num(self.inner) * 0.5)

    def _braced(self, k: int, segments: list[tuple[E, E]]) -> tuple[bool, bool]:
        """Whether the segment gets a brace at its left and right end."""
        s0, s1 = segments[k]
        need = 2 * (self._bay() + 2 * self.style.post) + self.style.post
        long_enough = self.ctx.low(s1 - s0) >= need
        left = long_enough and k == 0 and self.ctx.num(s0) == 0
        right = (
            long_enough
            and k == len(segments) - 1
            and abs(self.ctx.num(s1) - self.ctx.num(self.length)) < 0.5
        )
        return left, right

    def _segment(self, k: int, s0: E, s1: E, braced: tuple[bool, bool]) -> None:
        st = self.style
        left, right = braced
        lo, hi = s0, s1
        tag = str(k)
        if left:
            lo = s0 + st.post + self._bay()
            self.box(f"pcl{tag}", "Eckpfosten", self.post_lumber, s0, st.plate, st.post, self.inner)
            self._brace(f"bl{tag}", s0 + st.post, lo)
        if right:
            hi = s1 - st.post - self._bay()
            self.box(
                f"pcr{tag}",
                "Eckpfosten",
                self.post_lumber,
                s1 - st.post,
                st.plate,
                st.post,
                self.inner,
            )
            self._brace(f"br{tag}", s1 - st.post, hi)
        count, pitch = self.posts(f"post{tag}", lo, hi, st.plate, self.inner)
        if st.infill and count >= 2 and self.ctx.num(pitch - st.post) >= MIN_INFILL_MM:
            self.box(
                f"fill{tag}",
                f"Gefach {self.label}",
                st.infill,
                lo + st.post + pitch * e("i"),
                st.plate,
                pitch - st.post,
                self.inner,
                count=count - 1,
            )

    def _brace(self, id: str, ua: E, ub: E) -> None:
        """Diagonal from the corner post (``ua``, low) to the next post (``ub``, high), with
        vertical end faces so that both ends touch the post faces."""
        st, ctx = self.style, self.ctx
        thin, wide = st.brace
        run = abs(ctx.num(ub - ua))
        # Steepest case: the wall at the upper end of its range (sliders), so the end faces stay
        # clear of the plates there, too.
        rise_default = ctx.big(self.inner) - wide * 2.4
        cos = run / math.hypot(run, rise_default)
        half = wide / 2 / cos + 2  # half the vertical extent of an end face
        z_low = st.plate + half
        z_high = self.height - st.plate - half
        v = self.v0 + st.thickness / 2
        member(
            self.out,
            self.ax,
            self.prefix + id,
            f"Strebe {self.label}",
            ctx.lumber(thin, wide),
            (self.u0 + ua, v, self.z0 + z_low),
            (self.u0 + ub, v, self.z0 + z_high),
            cuts=("plumb", "plumb"),
        )

    def _opening(self, j: int, item: Open, start: E, end: E) -> None:
        st, ctx = self.style, self.ctx
        piece, width, height, sill = OPENING_SIZES[item.kind]
        bottom = st.plate + sill  # z of the opening's lower edge
        top = bottom + height
        gap = self.height - st.plate - top  # between the opening and the top plate
        if ctx.num(gap) < 80:
            raise BlockError(
                f"Wand {self.label}: {item.kind} ({height} mm hoch) passt nicht unter den Rähm – "
                f"Wandhöhe mindestens {top + st.plate + 80:.0f} mm"
            )
        t, tag = st.thickness, str(j)
        # Header over the opening, short posts above it.
        head = min(HEADER_MM, round(ctx.num(gap)))
        self.box(
            f"head{tag}", f"Sturz {self.label}", self.ctx.lumber(head, t), start, top, width, head
        )
        self.posts(
            f"top{tag}",
            start,
            end,
            top + head,
            gap - head,
            name="Stiel über Sturz",
            when=f"{(gap - head).text} > {MIN_GAP_MM}",
        )
        if sill:
            rail = self.ctx.lumber(RAIL_MM, t)
            self.box(
                f"rail{tag}",
                f"Brüstungsriegel {self.label}",
                rail,
                start,
                bottom - RAIL_MM,
                width,
                RAIL_MM,
            )
            self.posts(
                f"low{tag}", start, end, st.plate, sill - RAIL_MM, name="Stiel unter Fenster"
            )
        self.box(
            f"open{tag}",
            "Tür" if item.kind == "door" else "Fenster",
            piece,
            start,
            bottom,
            width,
            height,
            v=(t - PIECE_DEPTH) / 2,
            dv=PIECE_DEPTH,
        )

    def _cladding(self, ranges: list[tuple[Open, E, E]], outside: int) -> None:
        st = self.style
        cutouts = []
        for item, start, _end in ranges:
            _, width, height, sill = OPENING_SIZES[item.kind]
            cutouts.append(
                Cutout(
                    kind="rect",
                    at=(start.expr(), st.plate + sill),
                    size=(width, height),
                )
            )
        v = -CLADDING_MM if outside < 0 else st.thickness
        self.box(
            "clad",
            f"Schalung {self.label}",
            CLADDING,
            0,
            0,
            self.length,
            self.height,
            v=v,
            dv=CLADDING_MM,
            cutouts=cutouts,
        )
