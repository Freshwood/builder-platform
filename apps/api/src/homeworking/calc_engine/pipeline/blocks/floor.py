"""Floor on pad footings: pads, bearers, joists and a sheet deck.

Layers from the ground up: concrete pads (150), bearers along x (160), joists along y (140), OSB
sheets (18). Footprint (0 .. W) x (0 .. D); the top of the deck is ``FLOOR_MM``.
"""

from __future__ import annotations

import math

from homeworking.calc_engine.pipeline.blocks.kit import Axes, Ctx, Out, box, long_box
from homeworking.calc_engine.pipeline.blocks.sym import Num, e

PAD_MM = 300
PAD_H = 150
BEARER_W, BEARER_H = 100, 160
JOIST_W, JOIST_H = 60, 140
DECK_MM = 18
DECK_SHEET = "osb_18"
SHEET_X, SHEET_Y = 2500, 1250
PAD_SPACING = 1800
BEARER_SPACING = 1600
JOIST_SPACING = 450
FLOOR_MM = PAD_H + BEARER_H + JOIST_H + DECK_MM
AX_X = Axes("x")
AX_Y = Axes("y")


def floor(
    out: Out, ctx: Ctx, *, prefix: str, u0: Num, v0: Num, z0: Num, width: Num, depth: Num
) -> None:
    """Floor under a building of ``width`` (x) and ``depth`` (y), lower corner at (u0, v0, z0)."""
    x, z = AX_X, e(z0)
    w, d = e(width), e(depth)
    nw, nd = ctx.num(w), ctx.num(d)
    rows = max(2, math.ceil((nd - BEARER_W) / BEARER_SPACING) + 1)
    cols = max(2, math.ceil((nw - PAD_MM) / PAD_SPACING) + 1)
    joists = max(2, math.ceil((nw - JOIST_W) / JOIST_SPACING) + 1)
    # Pads: a grid under the bearers.
    pitch_x = (w - PAD_MM) / (cols - 1)
    pitch_y = (d - PAD_MM) / (rows - 1)
    box(
        out,
        x,
        prefix + "pad",
        "Punktfundament",
        "concrete_c25",
        (e(u0) + pitch_x * e(f"i % {cols}"), e(v0) + pitch_y * e(f"i // {cols}"), z),
        (PAD_MM, PAD_MM, PAD_H),
        repeat=(rows * cols, "i"),
    )
    # Bearers along x, one per pad row.
    lum_bearer = ctx.lumber(BEARER_W, BEARER_H)
    long_box(
        out,
        x,
        ctx,
        prefix + "bear",
        "Unterzug",
        lum_bearer,
        u0,
        w,
        lambda r: e(v0) + (d - BEARER_W) / (rows - 1) * r,
        z + PAD_H,
        BEARER_W,
        BEARER_H,
        rows=rows,
    )
    # Joists along y.
    lum_joist = ctx.lumber(JOIST_W, JOIST_H)
    long_box(
        out,
        AX_Y,
        ctx,
        prefix + "joist",
        "Bodenbalken",
        lum_joist,
        v0,
        d,
        lambda r: e(u0) + (w - JOIST_W) / (joists - 1) * r,
        z + PAD_H + BEARER_H,
        JOIST_W,
        JOIST_H,
        rows=joists,
    )
    # Deck: sheets tiled over the joists.
    nx = max(1, math.ceil(ctx.big(w) / SHEET_X))
    ny = max(1, math.ceil(ctx.big(d) / SHEET_Y))
    box(
        out,
        x,
        prefix + "deck",
        "Bodenplatte",
        DECK_SHEET,
        (
            e(u0) + w / nx * e(f"i % {nx}"),
            e(v0) + d / ny * e(f"i // {nx}"),
            z + PAD_H + BEARER_H + JOIST_H,
        ),
        (w / nx, d / ny, DECK_MM),
        repeat=(nx * ny, "i"),
    )
