"""A complete small building: floor on pads, four framed walls and a roof.

The module box gives width (x), depth (y) and total height (floor to ridge). The engine chooses the
wall height and the roof pitch so that the total height fits, and places door and windows.
"""

from __future__ import annotations

import math

from homeworking.calc_engine.pipeline.blocks.floor import FLOOR_MM, floor
from homeworking.calc_engine.pipeline.blocks.kit import Axes, BlockError, Ctx, Out
from homeworking.calc_engine.pipeline.blocks.roof import (
    COVER,
    MAX_PITCH,
    MAX_SPAN_MM,
    MIN_PITCH,
    OVERHANG_MM,
    RIDGE_W,
    TIE_H,
    gable_roof,
    tan,
)
from homeworking.calc_engine.pipeline.blocks.sym import E, e
from homeworking.calc_engine.pipeline.blocks.wall import STYLES, Open, Wall
from homeworking.construction_model.pipeline import BlockSpec, Opening

WALL_MIN_MM = {"fachwerk": 2500, "stud": 2400}
WALL_WISH_MM: dict[str, float] = {"fachwerk": 2600, "stud": 2500}
WALL_MAX_MM = 3400
FLAT_ROOF_MM = 140 + 24  # ties and slab


def default_openings(width: float, depth: float, style: str) -> list[Opening]:
    """A door in the front, a window in each side wall and one in the back, where they fit."""
    post = STYLES[style].post
    items = [Opening(wall="front", kind="door", at=None)]
    side = depth - 2 * STYLES[style].thickness
    if side >= 800 + 4 * post:
        items += [
            Opening(wall="left", kind="window", at=None),
            Opening(wall="right", kind="window", at=None),
        ]
    if width >= 1000 + 800 + 6 * post + 600:
        items.append(Opening(wall="back", kind="window", at=None))
    return items


def _openings(items: list[Opening], wall: str, length: E, shift: float) -> list[Open]:
    """The openings of one wall; ``at`` counts from the building's corner, evenly spaced if open."""
    mine = [o for o in items if o.wall == wall]
    out = []
    for j, o in enumerate(mine):
        centre = length * ((j + 0.5) / len(mine)) if o.at is None else e(o.at - shift)
        out.append(Open(o.kind, centre))
    return out


def _along(nw: float, nd: float) -> str:
    return "x" if nw >= nd else "y"


def _wall_height(spec: BlockSpec, nw: float, nd: float, nh: float) -> float:
    """Wall height (top of the top plates above the floor) for the default total height.

    Gable roof: the usual wall height, unless the roof would end up flatter or steeper than its
    useful range; then the wall gives way. Flat roof: what is left of the total height."""
    if spec.roof == "flat":
        wall_h = nh - FLOOR_MM - FLAT_ROOF_MM
        if wall_h < WALL_MIN_MM[spec.frame]:
            need = WALL_MIN_MM[spec.frame] + FLOOR_MM + FLAT_ROOF_MM
            raise BlockError(
                f"Haus: Gesamthöhe {nh:.0f} mm ist zu niedrig (mindestens {need:.0f} mm)"
            )
        if wall_h > WALL_MAX_MM:
            raise BlockError(
                f"Haus: Gesamthöhe {nh:.0f} mm ist für ein Flachdach zu groß "
                f"(höchstens {WALL_MAX_MM + FLOOR_MM + FLAT_ROOF_MM} mm)"
            )
        return wall_h
    span = nd if _along(nw, nd) == "x" else nw
    run = span / 2 - RIDGE_W / 2 + OVERHANG_MM
    wall_h = float(WALL_WISH_MM[spec.frame])
    rise = nh - FLOOR_MM - wall_h
    low, high = TIE_H + tan(MIN_PITCH) * run, TIE_H + tan(MAX_PITCH) * run
    wall_h += min(0.0, rise - low) + max(0.0, rise - high)
    if wall_h < WALL_MIN_MM[spec.frame]:
        need_mm = WALL_MIN_MM[spec.frame] + FLOOR_MM + low
        raise BlockError(
            f"Haus: Gesamthöhe {nh:.0f} mm ist zu niedrig für Boden, Wand und Satteldach "
            f"(mindestens {math.ceil(need_mm / 100) * 100} mm, oder roof=flat)"
        )
    if wall_h > WALL_MAX_MM:
        raise BlockError(
            f"Haus: Gesamthöhe {nh:.0f} mm ist zu groß für diese Spannweite – Höhe verringern"
        )
    return wall_h


def house(out: Out, ctx: Ctx, spec: BlockSpec, size: tuple[E, E, E]) -> E:
    """Write the building into ``out``; returns its overall height (floor to ridge) as expression."""
    style = STYLES[spec.frame]
    w, d, h = size
    nw, nd, nh = ctx.num(w), ctx.num(d), ctx.num(h)
    t = style.thickness
    if min(nw, nd) < 2000:
        raise BlockError("Haus: Breite und Tiefe mindestens 2000 mm")
    along = _along(nw, nd)
    span = d if along == "x" else w
    length = w if along == "x" else d
    wall_h = _wall_height(spec, nw, nd, nh)
    # A gable roof sits on walls of a fixed height; a flat roof takes what the total height leaves.
    wall_expr = e(round(wall_h)) if spec.roof == "gable" else h - FLOOR_MM - FLAT_ROOF_MM

    items = spec.openings if spec.openings is not None else default_openings(nw, nd, spec.frame)
    floor(out, ctx, prefix="fl", u0=0, v0=0, z0=0, width=w, depth=d)

    side = d - 2 * t
    layout: list[tuple[str, str, E | float, E | float, E | float, int, str, float]] = [
        ("front", "x", 0, 0, w, -1, "vorne", 0.0),
        ("back", "x", 0, d - t, w, +1, "hinten", 0.0),
        ("left", "y", t, 0, side, -1, "links", float(t)),
        ("right", "y", t, w - t, side, +1, "rechts", float(t)),
    ]
    for key, orient, u0, v0, wall_len, outside, label, shift in layout:
        ax = Axes(orient)  # type: ignore[arg-type]
        builder = Wall(
            out,
            ax,
            ctx,
            prefix=key[0] + "_",
            origin=(u0, v0, FLOOR_MM),
            length=wall_len,
            height=wall_expr,
            style=style,
            label=label,
        )
        builder.build(
            _openings(items, key, e(wall_len), shift), braces=spec.braces, outside=outside
        )

    if spec.roof == "gable":
        gable_roof(
            out,
            ctx,
            prefix="ro_",
            along=along,
            origin=(0, 0, e(FLOOR_MM) + wall_expr),
            length=length,
            span=span,
            ridge_rise=h - FLOOR_MM - wall_expr,
            cover=spec.cover,
        )
    else:
        flat_roof(out, ctx, w, d, e(FLOOR_MM) + wall_expr)
    return h


def flat_roof(out: Out, ctx: Ctx, w: E, d: E, z0: E) -> None:
    """Ties across the short side and a covering slab on top."""
    from homeworking.calc_engine.pipeline.blocks.kit import box, long_box
    from homeworking.calc_engine.pipeline.blocks.roof import TIE_H, TIE_W

    along = "x" if ctx.num(w) >= ctx.num(d) else "y"
    ax = Axes(along)  # type: ignore[arg-type]
    cross = Axes("y" if along == "x" else "x")
    length, span = (w, d) if along == "x" else (d, w)
    n = max(2, math.ceil((ctx.num(length) - TIE_W) / 900) + 1)
    long_box(
        out,
        cross,
        ctx,
        "ro_tie",
        "Dachbalken",
        ctx.lumber(TIE_W, TIE_H),
        -OVERHANG_MM,
        span + 2 * OVERHANG_MM,
        lambda r: (length - TIE_W) / (n - 1) * r,
        z0,
        TIE_W,
        TIE_H,
        rows=n,
    )
    material, thick = COVER["boards"]
    box(
        out,
        ax,
        "ro_cover",
        "Dacheindeckung",
        material,
        (0, -OVERHANG_MM, z0 + TIE_H),
        (length, span + 2 * OVERHANG_MM, thick),
    )


def height_bounds(spec: BlockSpec, width: float, depth: float) -> tuple[float, float]:
    """Smallest and largest total height the house can have at this footprint."""
    wall_min, wall_max = WALL_MIN_MM[spec.frame], WALL_MAX_MM
    if spec.roof == "flat":
        return (
            float(wall_min + FLOOR_MM + FLAT_ROOF_MM),
            float(wall_max + FLOOR_MM + FLAT_ROOF_MM),
        )
    span = depth if _along(width, depth) == "x" else width
    run = span / 2 - RIDGE_W / 2 + OVERHANG_MM
    return (
        wall_min + FLOOR_MM + TIE_H + tan(MIN_PITCH) * run,
        wall_max + FLOOR_MM + TIE_H + tan(MAX_PITCH) * run,
    )


def house_limits(spec: BlockSpec, env: dict[str, float]) -> dict[str, tuple[float, float]]:
    """Range of each dimension parameter around its default that the house can follow.

    A quarter either way; a gable roof adapts its pitch, a flat roof keeps the wall above its
    smallest useful height. Rafters and ties limit the span."""
    nw, nd, nh = (float(env[k]) for k in ("width_mm", "depth_mm", "height_mm"))
    _wall_height(spec, nw, nd, nh)  # the default itself must work
    cap = MAX_SPAN_MM - 600
    limits = {
        "width_mm": (max(nw * 0.75, 2400.0), nw * 1.25),
        "depth_mm": (max(nd * 0.75, 2400.0), nd * 1.25),
    }
    if spec.roof == "gable":
        span = "depth_mm" if _along(nw, nd) == "x" else "width_mm"
        limits[span] = (limits[span][0], min(limits[span][1], float(cap)))
        low, high = nh * 0.75, nh * 1.25
    else:
        low = max(nh * 0.75, WALL_MIN_MM[spec.frame] + FLOOR_MM + FLAT_ROOF_MM)
        high = min(nh * 1.25, WALL_MAX_MM + FLOOR_MM + FLAT_ROOF_MM)
    limits["height_mm"] = (low, high)
    return limits


# Build steps of a house: (title, text, id prefixes of the parts).
STEPS = (
    (
        "Fundament und Boden",
        "Punktfundamente setzen und ausrichten, Unterzüge und Bodenbalken verlegen, die "
        "Bodenplatten verschrauben. Diagonalen messen, bis der Boden rechtwinklig und eben ist.",
        ("fl",),
    ),
    (
        "Wände aufstellen",
        "Schwellen und Pfosten der vier Wände am Boden vormontieren, aufrichten, ausrichten und "
        "an den Ecken verbinden; Streben, Ausfachung bzw. Schalung, Türen und Fenster einsetzen.",
        ("f_", "b_", "l_", "r_"),
    ),
    (
        "Dach",
        "Dachbalken auf die Rähme legen, Sparren aufstellen und am First verbinden, Dach eindecken "
        "und die Giebel schließen.",
        ("ro_",),
    ),
)


def steps(local_ids: list[str]) -> list[tuple[str, str, list[str]]]:
    """Build steps for the given part ids (local to the module), in construction order."""
    result = []
    for title, text, prefixes in STEPS:
        ids = [i for i in local_ids if i.startswith(prefixes)]
        if ids:
            result.append((title, text, ids))
    return result
