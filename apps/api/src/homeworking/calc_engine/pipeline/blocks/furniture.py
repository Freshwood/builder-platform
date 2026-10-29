"""Furniture blocks: carcass (shelf, cabinet), platform (podium) and table (also bench).

All three fill the module box width (x) x depth (y) x height (z) and are made of sheets and
lumber whose free dimension follows the parameters, so every slider keeps working.
"""

from __future__ import annotations

import math

from homeworking.calc_engine.pipeline.blocks.kit import Axes, BlockError, Ctx, Out, box
from homeworking.calc_engine.pipeline.blocks.sym import E, e
from homeworking.construction_model.assembly import HardwareSpec
from homeworking.construction_model.pipeline import BlockSpec

AX = Axes("x")
PANEL = "plywood_birch_18"
PANEL_MM = 18
BACK = "hdf_3"
BACK_MM = 3
SHEET = (2500, 1250)  # format of the plywood and hdf sheets
DOOR_GAP = 3


def _fits(what: str, a: float, b: float, limit: tuple[int, int] = SHEET) -> None:
    long, short = max(a, b), min(a, b)
    if long > limit[0] or short > limit[1]:
        raise BlockError(
            f"{what}: {a:.0f} x {b:.0f} mm passt nicht auf eine Platte ({limit[0]} x {limit[1]} mm) "
            "– Maße verkleinern"
        )


def tiles(ctx: Ctx, a: E, b: E, fmt: tuple[int, int]) -> tuple[int, int]:
    """Fewest equal pieces (along a, along b) that all fit on a sheet of ``fmt``, either way round,
    for the upper end of the dimension range."""
    na_, nb_ = ctx.big(a), ctx.big(b)
    best: tuple[int, int] | None = None
    for ka in range(1, 9):
        for kb in range(1, 9):
            long, short = max(na_ / ka, nb_ / kb), min(na_ / ka, nb_ / kb)
            if long <= fmt[0] and short <= fmt[1] and (best is None or ka * kb < best[0] * best[1]):
                best = (ka, kb)
    if best is None:
        raise BlockError(f"Platte {na_:.0f} x {nb_:.0f} mm ist zu groß für das Plattenformat")
    return best


def carcass(out: Out, ctx: Ctx, spec: BlockSpec, size: tuple[E, E, E]) -> None:
    """Sides, bottom, top, dividers, shelves, back panel and optional doors."""
    w, d, h = size
    nh = ctx.num(h)
    t, cols, shelves = PANEL_MM, spec.columns, spec.shelves
    inner = w - 2 * t
    col_w = (inner - (cols - 1) * t) / cols
    depth = d - BACK_MM if spec.back else d
    if ctx.num(col_w) < 120 or nh < 3 * t + 60:
        raise BlockError(
            "Korpus: zu klein für Spalten und Böden – Maße vergrößern oder weniger Spalten"
        )
    _fits("Seitenteil", ctx.big(h), ctx.big(depth))
    _fits("Boden", ctx.big(col_w), ctx.big(depth))
    pitch = col_w + t
    box(
        out,
        AX,
        "side",
        "Seitenteil",
        PANEL,
        (e("i") * (w - t), 0, 0),
        (t, depth, h),
        repeat=(2, "i"),
    )
    for ident, name, z in (("bot", "Boden", 0), ("top", "Deckel", h - t)):
        box(
            out,
            AX,
            ident,
            name,
            PANEL,
            (t + pitch * e("i"), 0, z),
            (col_w, depth, t),
            repeat=(cols, "i"),
        )
    if cols > 1:
        box(
            out,
            AX,
            "div",
            "Trennwand",
            PANEL,
            (t + col_w + pitch * e("i"), 0, t),
            (t, depth, h - 2 * t),
            repeat=(cols - 1, "i"),
        )
    if shelves:
        gap = (h - 2 * t - shelves * t) / (shelves + 1)
        box(
            out,
            AX,
            "shelf",
            "Fachboden",
            PANEL,
            (
                t + pitch * e(f"i // {shelves}"),
                0,
                t + gap * e(f"i % {shelves} + 1") + t * e(f"i % {shelves}"),
            ),
            (col_w, depth, t),
            repeat=(cols * shelves, "i"),
        )
    if spec.back:
        nx, nz = tiles(ctx, w, h, SHEET)
        box(
            out,
            AX,
            "back",
            "Rückwand",
            BACK,
            (w / nx * e(f"i % {nx}"), depth, h / nz * e(f"i // {nx}")),
            (w / nx, BACK_MM, h / nz),
            repeat=(nx * nz, "i"),
        )
    if spec.doors:
        door_w = w / cols - 2 * DOOR_GAP
        box(
            out,
            AX,
            "door",
            "Tür",
            PANEL,
            (w / cols * e("i") + DOOR_GAP, -t, DOOR_GAP),
            (door_w, t, h - 2 * DOOR_GAP),
            repeat=(cols, "i"),
        )
        out.hardware.append(
            HardwareSpec(item="hinge_cabinet_35", quantity=f"{cols} * if({h.text} > 1000, 3, 2)")
        )
        out.hardware.append(HardwareSpec(item="handle_pull_128", quantity=cols))


def platform(out: Out, ctx: Ctx, spec: BlockSpec, size: tuple[E, E, E]) -> None:
    """A box of plywood skirts and ribs with a deck on top (podium, stage, step)."""
    w, d, h = size
    nw, nd, nh = ctx.num(w), ctx.num(d), ctx.num(h)
    t, deck = PANEL_MM, 24
    if nh < 100 or min(nw, nd) < 300:
        raise BlockError("Podest: mindestens 100 mm hoch und 300 x 300 mm groß")
    body = h - deck  # height of skirts and ribs
    _fits("Zarge", ctx.big(d) - 2 * t, ctx.big(body))
    ribs = max(0, math.ceil(ctx.big(w) / 600) - 1)
    pieces = max(1, math.ceil(ctx.big(w) / SHEET[0]))
    _fits("Zarge", ctx.big(w) / pieces, ctx.big(body))
    box(
        out,
        AX,
        "skf",
        "Zarge",
        PANEL,
        (w / pieces * e(f"i % {pieces}"), (d - t) * e(f"i // {pieces}"), 0),
        (w / pieces, t, body),
        repeat=(2 * pieces, "i"),
    )
    box(
        out,
        AX,
        "sks",
        "Zarge seitlich",
        PANEL,
        (e("i") * (w - t), t, 0),
        (t, d - 2 * t, body),
        repeat=(2, "i"),
    )
    if ribs:
        step = (w - t) / (ribs + 1)
        box(
            out,
            AX,
            "rib",
            "Rippe",
            PANEL,
            (step * (e("i") + 1), t, 0),
            (t, d - 2 * t, body),
            repeat=(ribs, "i"),
        )
    nx, ny = tiles(ctx, w, d, SHEET)
    # The customer may choose between a panel and boards (parameter "surface", added by prepare).
    chosen = "surface" in ctx.env
    box(
        out,
        AX,
        "deck",
        "Trittfläche",
        "plywood_birch_24",
        (w / nx * e(f"i % {nx}"), d / ny * e(f"i // {nx}"), body),
        (w / nx, d / ny, deck),
        repeat=(nx * ny, "i"),
        when="surface == 'panel'" if chosen else None,
    )
    if chosen:
        # Boards run along x and touch edge to edge. They are modelled as strips of 24 mm larch
        # boarding (priced per m², any width), so their width follows the depth exactly and the
        # deck stays closed at every slider position.
        n = max(2, math.ceil(ctx.big(d) / BOARD_MM))
        box(
            out,
            AX,
            "plank",
            "Brett",
            "cladding_larch_24",
            (0, d / n * e("i"), body),
            (w, d / n, deck),
            repeat=(n, "i"),
            when="surface == 'boards'",
        )


BOARD_MM = 130  # about the width of a floorboard


LEG_MM = 70
TOP_MM = 28
APRON = (28, 80)
TOP_SHEET = "glulam_spruce_28"
TOP_FORMAT = (2000, 600)


def table(out: Out, ctx: Ctx, spec: BlockSpec, size: tuple[E, E, E]) -> None:
    """Top of glued panels, four legs and an apron frame (table, bench, desk, workbench)."""
    w, d, h = size
    nw, nd, nh = ctx.num(w), ctx.num(d), ctx.num(h)
    if min(nw, nd) < 2 * LEG_MM + 100 or nh < 200 + TOP_MM:
        raise BlockError("Tisch: Breite und Tiefe mindestens 240 mm, Höhe mindestens 230 mm")
    wood = ctx.wood
    leg_h = h - TOP_MM
    box(
        out,
        AX,
        "leg",
        "Tischbein",
        f"lumber_{wood}_{LEG_MM}x{LEG_MM}",
        ((w - LEG_MM) * e("i % 2"), (d - LEG_MM) * e("i // 2"), 0),
        (LEG_MM, LEG_MM, leg_h),
        repeat=(4, "i"),
    )
    apron = ctx.lumber(*APRON)
    z = leg_h - APRON[1]
    box(
        out,
        AX,
        "apf",
        "Zarge vorn/hinten",
        apron,
        (LEG_MM, (d - APRON[0]) * e("i"), z),
        (w - 2 * LEG_MM, APRON[0], APRON[1]),
        repeat=(2, "i"),
    )
    box(
        out,
        AX,
        "aps",
        "Zarge seitlich",
        apron,
        ((w - APRON[0]) * e("i"), LEG_MM, z),
        (APRON[0], d - 2 * LEG_MM, APRON[1]),
        repeat=(2, "i"),
    )
    nx, ny = tiles(ctx, w, d, TOP_FORMAT)
    box(
        out,
        AX,
        "top",
        "Tischplatte",
        TOP_SHEET,
        (w / nx * e(f"i % {nx}"), d / ny * e(f"i // {nx}"), leg_h),
        (w / nx, d / ny, TOP_MM),
        repeat=(nx * ny, "i"),
    )
    if spec.lower_shelf:
        _fits("Ablageboden", ctx.big(w) - 2 * LEG_MM, ctx.big(d))
        # Full depth: the shelf touches the legs' inner faces along their whole width.
        box(
            out,
            AX,
            "shelf",
            "Ablageboden",
            PANEL,
            (LEG_MM, 0, e(150)),
            (w - 2 * LEG_MM, d, PANEL_MM),
        )


STEPS = {
    "post_frame": (
        (
            "Pfosten und Pfetten",
            "Pfosten lotrecht setzen (Fundament oder Pfostenträger), Pfetten auflegen "
            "und verschrauben, Diagonalen messen.",
            ("pf", "pb", "bf", "bb"),
        ),
        (
            "Sparren und Dach",
            "Sparren im gleichen Abstand auflegen und befestigen, bei Pultdach eindecken.",
            ("raft", "cover"),
        ),
    ),
    "fence": (
        ("Pfosten setzen", "Pfosten in Flucht und Höhe setzen und gut einbetten.", ("post",)),
        (
            "Riegel und Latten",
            "Riegel zwischen die Pfosten schrauben, Latten senkrecht aufschrauben.",
            ("rail", "board"),
        ),
    ),
    "carcass": (
        (
            "Korpus bauen",
            "Seitenteile, Boden und Deckel verbinden, Trennwände und Fachböden einsetzen, "
            "Diagonalen messen und rechtwinklig ausrichten.",
            ("side", "bot", "top", "div", "shelf"),
        ),
        (
            "Rückwand und Türen",
            "Rückwand aufnageln oder -schrauben, dann Türen und Beschläge montieren.",
            ("back", "door"),
        ),
    ),
    "platform": (
        (
            "Rahmen bauen",
            "Zargen und Rippen im Abstand von höchstens 60 cm verschrauben, Diagonalen messen.",
            ("skf", "sks", "rib"),
        ),
        (
            "Trittfläche auflegen",
            "Platten bündig auflegen und mit der Unterkonstruktion verschrauben.",
            ("deck", "plank"),
        ),
    ),
    "table": (
        (
            "Gestell bauen",
            "Beine und Zargen verbinden; Beine stehen bündig in den Ecken.",
            ("leg", "apf", "aps", "shelf"),
        ),
        ("Platte montieren", "Platte auflegen, ausrichten und von unten verschrauben.", ("top",)),
    ),
}
