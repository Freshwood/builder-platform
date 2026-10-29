"""Post-and-beam structures: pergola, carport, shelter (``post_frame``) and fence (``fence``).

Both write members whose length is the free dimension and whose section is fixed, so the sliders
move them without breaking a section. A shed roof uses the same slope expression as the house roof:
clamped between 12 and 30 degrees, so no slider position breaks it.
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
from homeworking.calc_engine.pipeline.blocks.roof import COVER, tan
from homeworking.calc_engine.pipeline.blocks.sym import E, call, e
from homeworking.construction_model.pipeline import BlockSpec

AX = Axes("x")
AY = Axes("y")
POST = 120
BEAM_H = 180
RAFTER_W, RAFTER_H = 60, 160
OVERHANG_MM = 300
LOW_CLEAR_MM = 2000  # clear height under the low beam of a shed roof
POST_SPACING = 3000
RAFTER_SPACING = 600  # pergola rafters; on a shed roof the covering lies on them
MIN_PITCH, MAX_PITCH = 12.0, 30.0  # a level cut needs a member steeper than 10 degrees
PERGOLA_RAFTER_H = 120
SHED_SPAN_MAX_MM = 8000  # (span + overhang) / cos(30 degrees) stays below the 13 m of KVH


def post_frame(out: Out, ctx: Ctx, spec: BlockSpec, size: tuple[E, E, E]) -> None:
    """Posts in two rows, a beam on each row, rafters across and (shed roof) a covering.

    The beams run along the longer side, the rafters span the shorter one. In the wall frame used
    here ``u`` runs along the beams and ``v`` across them (see ``Axes``)."""
    w, d, h = size
    nw, nd = ctx.num(w), ctx.num(d)
    if min(nw, nd) < 1500:
        raise BlockError("Pfostenbau: Breite und Tiefe mindestens 1500 mm")
    if spec.roof not in ("flat", "shed"):
        raise BlockError("Pfostenbau: roof muss flat (Pergola) oder shed (Pultdach) sein")
    ax, cross = (Axes("x"), Axes("y")) if nw >= nd else (Axes("y"), Axes("x"))
    along = ax.along
    length, span = (w, d) if along == "x" else (d, w)
    ov = OVERHANG_MM
    n_posts = max(2, math.ceil((ctx.big(length) - POST) / POST_SPACING) + 1)
    n_rafters = max(2, math.ceil((ctx.big(length) - RAFTER_W) / RAFTER_SPACING) + 1)
    post_lum = f"lumber_{ctx.wood}_{POST}x{POST}"
    beam_lum, beam_limit = ctx.long_lumber(POST, BEAM_H, ctx.big(length))
    yb = span - POST  # front face of the back beam
    rp = (length - RAFTER_W) / (n_rafters - 1)

    if spec.roof == "flat":
        z_low = z_high = h - BEAM_H - PERGOLA_RAFTER_H
        if ctx.num(z_low) < 1800:
            raise BlockError("Pergola: Höhe mindestens 2100 mm")
    else:
        if ctx.num(span) > SHED_SPAN_MAX_MM:
            raise BlockError(
                f"Pultdach: Spannweite höchstens {SHED_SPAN_MAX_MM} mm (Sparrenlänge), "
                "für mehr zwei Dächer oder ein Satteldach planen"
            )
        if ctx.num(h) < LOW_CLEAR_MM + BEAM_H + 300:
            raise BlockError(f"Carport: Höhe mindestens {LOW_CLEAR_MM + BEAM_H + 300} mm")
        z_low = e(LOW_CLEAR_MM)
        zf = z_low + BEAM_H  # top of the front beam: foot level of the rafters
        t = call("max", tan(MIN_PITCH), call("min", tan(MAX_PITCH), (h - zf) / (yb + ov)))
        root = call("sqrt", 1 + t * t)
        half = RAFTER_H * root / 2
        zr = zf + t * (yb + ov)  # top of the back beam
        z_high = zr - BEAM_H  # height of the back posts

    pitch = (length - POST) / (n_posts - 1)
    for ident, name, v, height in (
        ("pf", "Pfosten vorn", 0, z_low),
        ("pb", "Pfosten hinten", span - POST, z_high),
    ):
        box(
            out,
            ax,
            ident,
            name,
            post_lum,
            (pitch * e("i"), v, 0),
            (POST, POST, height),
            repeat=(n_posts, "i"),
        )
    for ident, name, v, z in (
        ("bf", "Pfette vorn", 0, z_low),
        ("bb", "Pfette hinten", span - POST, z_high),
    ):
        long_box(
            out, ax, ctx, ident, name, beam_lum, 0, length, v, z, POST, BEAM_H, limit=beam_limit
        )

    if spec.roof == "flat":
        rafter_lum, rafter_limit = ctx.long_lumber(
            RAFTER_W, PERGOLA_RAFTER_H, ctx.big(span) + 2 * ov
        )
        long_box(
            out,
            cross,
            ctx,
            "raft",
            "Sparren",
            rafter_lum,
            -ov,
            span + 2 * ov,
            lambda r: rp * r,
            z_low + BEAM_H,
            RAFTER_W,
            PERGOLA_RAFTER_H,
            rows=n_rafters,
            limit=rafter_limit,
        )
        return
    rafter_lum, _ = ctx.long_lumber(
        RAFTER_W, RAFTER_H, (ctx.big(span) + ov) * math.sqrt(1 + tan(MAX_PITCH) ** 2)
    )
    member(
        out,
        ax,
        "raft",
        "Sparren",
        rafter_lum,
        (rp * e("i") + RAFTER_W / 2, -ov + half / t, zf),
        (rp * e("i") + RAFTER_W / 2, yb, zr - half),
        cuts=("level", "plumb"),
        repeat=(n_rafters, "i"),
    )
    material, thick = COVER[spec.cover]
    lift = thick * root / 2
    member(
        out,
        ax,
        "cover",
        "Dacheindeckung",
        material,
        (length / 2, -ov, zf + lift),
        (length / 2, span, zf + t * (span + ov) + lift),
        section=(thick, length),
        facing="z",
        cuts=("plumb", "plumb"),
    )


FENCE_POST = 90
BOARD = (20, 120)  # thickness, width of a picket
BOARD_GAP_FACTOR = 1.4  # pitch of the pickets as multiple of their width at the default length
POST_GAP_MM = 2000


def fence(out: Out, ctx: Ctx, spec: BlockSpec, size: tuple[E, E, E]) -> None:
    """Posts, two rails and vertical pickets along x; the depth is the post thickness."""
    w, _, h = size
    nw, nh = ctx.num(w), ctx.num(h)
    if nw < 1000 or nh < 600:
        raise BlockError("Zaun: mindestens 1000 mm lang und 600 mm hoch")
    posts = max(2, math.ceil((ctx.big(w) - FENCE_POST) / POST_GAP_MM) + 1)
    pitch = (w - FENCE_POST) / (posts - 1)
    lum_post = f"lumber_{ctx.wood}_{FENCE_POST}x{FENCE_POST}"
    box(
        out,
        AX,
        "post",
        "Zaunpfosten",
        lum_post,
        (pitch * e("i"), 0, 0),
        (FENCE_POST, FENCE_POST, h),
        repeat=(posts, "i"),
    )
    rail_lum = ctx.lumber(40, 60)
    rails = 2
    box(
        out,
        AX,
        "rail",
        "Riegel",
        rail_lum,
        (FENCE_POST + pitch * e(f"i % {posts - 1}"), 0, 150 + (h - 450) * e(f"i // {posts - 1}")),
        (pitch - FENCE_POST, 40, 60),
        repeat=((posts - 1) * rails, "i"),
    )
    n = max(2, round(nw / (BOARD[1] * BOARD_GAP_FACTOR)))
    step = (w - BOARD[1]) / (n - 1)
    box(
        out,
        AX,
        "board",
        "Zaunlatte",
        ctx.lumber(*BOARD),
        (step * e("i"), -BOARD[0], 100),
        (BOARD[1], BOARD[0], h - 100),
        repeat=(n, "i"),
    )
