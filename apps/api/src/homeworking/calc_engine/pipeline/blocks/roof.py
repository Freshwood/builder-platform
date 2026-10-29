"""Gable roof on top of walls: ties, rafters, ridge board, covering and gable boards.

Roof frame: u along the ridge (0 .. length), v across (0 .. span), z up from the top of the walls'
top plates. Ties lie on the plates and carry the rafters; every rafter foot has a level cut that
sits on a tie, every rafter end a plumb cut that touches the ridge board.

The slope is an expression: it follows from the target ridge height and the span, clamped to a
useful range, so moving the width, depth or height slider changes the pitch and never breaks the
roof. Everything below is written for the top edge of the rafters, a straight line from the outer
end of the tie (``v = -overhang``) to the top of the ridge board.
"""

from __future__ import annotations

import math

from homeworking.calc_engine.pipeline.blocks.kit import (
    Axes,
    BlockError,
    Ctx,
    Out,
    box,
    long_box,
    member,
)
from homeworking.calc_engine.pipeline.blocks.sym import E, Num, call, e
from homeworking.construction_model.assembly import Shape

TIE_W, TIE_H = 60, 140
RAFTER_W, RAFTER_H = 60, 160  # thickness along the ridge, width in the slope plane
RIDGE_W = 60
OVERHANG_MM = 300
SPACING_MM = 900
MIN_PITCH, MAX_PITCH = 12.0, 45.0  # degrees; the rafter stays below the longest stock length
COVER = {"tiles": ("roof_tiles_clay", 60), "boards": ("cladding_larch_24", 24)}
GABLE = ("cladding_larch_24", 24)
MAX_SPAN_MM = 9600  # (span / 2 + overhang) / cos(45 degrees) stays below the 13 m of KVH


def tan(deg: float) -> float:
    return math.tan(math.radians(deg))


def slope(ridge_rise: Num, span: Num) -> E:
    """tan(pitch) for a ridge top ``ridge_rise`` above the plates, clamped to 12-45 degrees."""
    run = e(span) / 2 - RIDGE_W / 2 + OVERHANG_MM
    raw = (e(ridge_rise) - TIE_H) / run
    return call("max", tan(MIN_PITCH), call("min", tan(MAX_PITCH), raw))


def gable_roof(
    out: Out,
    ctx: Ctx,
    *,
    prefix: str,
    along: str,
    origin: tuple[Num, Num, Num],
    length: Num,
    span: Num,
    ridge_rise: Num,
    cover: str,
) -> None:
    """Write the roof; ``ridge_rise`` is the target height of the ridge top above ``origin`` z."""
    ax = Axes("x" if along == "x" else "y")  # u along the ridge
    cross = Axes("y" if along == "x" else "x")  # u across the ridge
    u0, v0, z0 = (e(o) for o in origin)
    ln, sp = e(length), e(span)
    ov = OVERHANG_MM
    if ctx.num(sp) > MAX_SPAN_MM - 600:
        raise BlockError(
            f"Dach: Spannweite {ctx.num(sp):.0f} mm ist für Sparren zu groß "
            f"(höchstens {MAX_SPAN_MM - 600} mm) – Haus schmaler planen"
        )
    n = max(2, math.ceil((ctx.num(ln) - RAFTER_W) / SPACING_MM) + 1)
    pitch_u = (ln - RAFTER_W) / (n - 1)

    t = slope(ridge_rise, sp)
    root = call("sqrt", 1 + t * t)  # 1 / cos(pitch)
    half = RAFTER_H * root / 2  # half the vertical extent of a rafter section
    zt = z0 + TIE_H  # top of the ties: foot level of the rafters
    yr = sp / 2 - RIDGE_W / 2  # where the rafters meet the ridge board
    zr = zt + t * (yr + ov)  # top of the ridge board = top edge of the rafters at yr
    zc = zr - half  # centre line of the rafter at yr
    ys = -ov + half / t  # centre line reaches the tie top (foot level) here

    # Beyond the usual stock length, members come as KVH instead of being cut into pieces.
    steepest = math.sqrt(1 + tan(MAX_PITCH) ** 2)
    tie_mat, tie_limit = ctx.long_lumber(TIE_W, TIE_H, ctx.big(sp) + 2 * ov)
    ridge_h = math.ceil(RAFTER_H * steepest + 20)
    ridge_mat, ridge_limit = ctx.long_lumber(RIDGE_W, ridge_h, ctx.big(ln))
    rafter_mat, _ = ctx.long_lumber(RAFTER_W, RAFTER_H, (ctx.big(sp) / 2 + ov) * steepest)
    # Ties across the ridge, resting on the plates of both long walls.
    long_box(
        out,
        cross,
        ctx,
        prefix + "tie",
        "Dachbalken",
        tie_mat,
        v0 - ov,
        sp + 2 * ov,
        lambda r: u0 + pitch_u * r,
        z0,
        TIE_W,
        TIE_H,
        rows=n,
        limit=tie_limit,
    )
    # Ridge board between the rafter pairs; tall enough for the steepest end face.
    long_box(
        out,
        ax,
        ctx,
        prefix + "ridge",
        "Firstbohle",
        ridge_mat,
        u0,
        ln,
        v0 + sp / 2 - RIDGE_W / 2,
        zr - ridge_h,
        RIDGE_W,
        ridge_h,
        limit=ridge_limit,
    )
    # Rafters: the front side rises with v, the back side is its mirror image.
    for side, (vs, ve) in (("f", (ys, yr)), ("b", (sp - ys, sp - yr))):
        member(
            out,
            ax,
            prefix + "raf" + side,
            "Sparren",
            rafter_mat,
            (u0 + pitch_u * e("i") + RAFTER_W / 2, v0 + vs, zt),
            (u0 + pitch_u * e("i") + RAFTER_W / 2, v0 + ve, zc),
            cuts=("level", "plumb"),
            repeat=(n, "i"),
        )
    # Covering: a slab on each slope, resting on the top edge of the rafters.
    material, thick = COVER[cover]
    lift = thick * root / 2  # centre line of the slab above the top edge, measured vertically
    z_start = zt + lift  # centre line height at v = -overhang
    z_end = zt + t * (sp / 2 + ov) + lift  # ... and at the ridge, v = span / 2
    for side in ("f", "b"):
        va, vb = (-ov, sp / 2) if side == "f" else (sp + ov, sp / 2)
        member(
            out,
            ax,
            prefix + "cov" + side,
            "Dacheindeckung",
            material,
            (u0 + ln / 2, v0 + va, z_start),
            (u0 + ln / 2, v0 + vb, z_end),
            section=(thick, ln),
            facing="z",
            cuts=("plumb", "plumb"),
        )
    # Gable boards close the triangles at both ends (outside the end rafters).
    for k, end in enumerate((e(-GABLE[1]), ln)):
        box(
            out,
            ax,
            f"{prefix}gab{k}",
            "Giebelschalung",
            GABLE[0],
            (u0 + end, v0, z0),
            (GABLE[1], sp, zc - z0),
            shape=Shape(kind="triangle"),
        )
