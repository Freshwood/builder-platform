"""Drawing IR for the raised bed: plan, front, side and corner detail."""

from __future__ import annotations

from calc_engine.packs.raised_bed.geometry import BOARD_T, BOARD_W, POST, RaisedBedGeometry
from construction_model.drawing import (
    Dimension,
    Drawing,
    Fill,
    Label,
    Line,
    Primitive,
    Rect,
    Stroke,
)

SLAB = 300
SLAB_T = 40
DIM_GAP = 140


def _mm(value: int) -> str:
    return f"{value}"


def _post_x_positions(g: RaisedBedGeometry) -> list[int]:
    """Left edges of all posts along a long side (corner and intermediate)."""
    left = BOARD_T
    right = g.p.length_mm - BOARD_T - POST
    mids = [x - POST // 2 for x in g.mid_positions]
    return [left, *mids, right]


def plan_view(g: RaisedBedGeometry) -> Drawing:
    length, width = g.p.length_mm, g.p.width_mm
    prims: list[Primitive] = [
        Rect(x=0, y=0, w=length, h=BOARD_T, fill=Fill.WOOD),
        Rect(x=0, y=width - BOARD_T, w=length, h=BOARD_T, fill=Fill.WOOD),
        Rect(x=0, y=BOARD_T, w=BOARD_T, h=width - 2 * BOARD_T, fill=Fill.WOOD),
        Rect(x=length - BOARD_T, y=BOARD_T, w=BOARD_T, h=width - 2 * BOARD_T, fill=Fill.WOOD),
    ]
    for x in _post_x_positions(g):
        prims.append(Rect(x=x, y=BOARD_T, w=POST, h=POST, fill=Fill.WOOD_END))
        prims.append(Rect(x=x, y=width - BOARD_T - POST, w=POST, h=POST, fill=Fill.WOOD_END))
    for x in g.mid_positions:
        prims.append(
            Line(x1=x, y1=BOARD_T + POST, x2=x, y2=width - BOARD_T - POST, stroke=Stroke.CENTER)
        )
    prims += [
        Dimension(x1=0, y1=width, x2=length, y2=width, offset=DIM_GAP, text=_mm(length)),
        Dimension(x1=length, y1=0, x2=length, y2=width, offset=DIM_GAP, text=_mm(width)),
        Dimension(
            x1=BOARD_T,
            y1=0,
            x2=length - BOARD_T,
            y2=0,
            offset=-DIM_GAP,
            text=f"innen {g.inner_length}",
        ),
        Label(x=length / 2, y=width / 2, text="Pflanzfläche", anchor="middle"),
        Label(
            x=length / 2,
            y=width / 2 + 90,
            text=f"{g.inner_length} × {g.inner_width}",
            anchor="middle",
            size="small",
        ),
    ]
    if g.mid_positions:
        prims.append(
            Label(
                x=g.mid_positions[0] + 30,
                y=width / 2 - 120,
                text="Zuganker M10",
                size="small",
            )
        )
    return Drawing(
        view="plan",
        title="Draufsicht",
        description=(
            f"Draufsicht des Hochbeets, außen {length} × {width} mm, innen "
            f"{g.inner_length} × {g.inner_width} mm, {g.post_count} Pfosten 70 × 70 mm"
            + (f", {g.mid_count} Zuganker-Achse(n)" if g.mid_count else "")
            + "."
        ),
        scale_hint="1:20",
        min_x=-DIM_GAP - 80,
        min_y=-DIM_GAP - 80,
        width=length + 2 * DIM_GAP + 200,
        height=width + 2 * DIM_GAP + 200,
        primitives=prims,
    )


def _elevation(
    g: RaisedBedGeometry, *, view: str, title: str, span: int, end_grain: bool, posts: list[int]
) -> Drawing:
    h = g.wall_height
    cap = BOARD_T if g.p.top_cap else 0
    prims: list[Primitive] = []
    board_x0, board_w = (BOARD_T, span - 2 * BOARD_T) if end_grain else (0, span)
    for row in range(g.rows):
        y = cap + row * BOARD_W
        prims.append(Rect(x=board_x0, y=y, w=board_w, h=BOARD_W, fill=Fill.WOOD))
        if end_grain:
            prims.append(Rect(x=0, y=y, w=BOARD_T, h=BOARD_W, fill=Fill.WOOD_END))
            prims.append(Rect(x=span - BOARD_T, y=y, w=BOARD_T, h=BOARD_W, fill=Fill.WOOD_END))
    if cap:
        prims.append(Rect(x=0, y=0, w=span, h=BOARD_T, fill=Fill.WOOD, label="Abdeckleiste"))
    for x in posts:
        prims.append(Rect(x=x, y=cap, w=POST, h=h, stroke=Stroke.HIDDEN))
    ground = cap + h + SLAB_T
    for x in posts:
        cx = x + POST / 2
        prims.append(
            Rect(x=cx - SLAB / 2, y=cap + h, w=SLAB, h=SLAB_T, fill=Fill.GROUND, stroke=Stroke.THIN)
        )
    prims += [
        Line(x1=-200, y1=ground, x2=span + 200, y2=ground, stroke=Stroke.OUTLINE),
        Dimension(x1=0, y1=ground, x2=span, y2=ground, offset=DIM_GAP, text=_mm(span)),
        Dimension(x1=span, y1=0, x2=span, y2=cap + h, offset=DIM_GAP + 60, text=_mm(cap + h)),
        Dimension(
            x1=0,
            y1=cap,
            x2=0,
            y2=cap + BOARD_W,
            offset=-DIM_GAP,
            text=_mm(BOARD_W),
        ),
        Label(x=-200, y=ground + 110, text="Gelände / Kiesbett", size="small"),
    ]
    return Drawing(
        view=view,
        title=title,
        description=(
            f"{title}: {g.rows} Brettreihen à {BOARD_W} mm, Wandhöhe {h} mm"
            + (f" plus Abdeckleiste {BOARD_T} mm" if cap else "")
            + f", Breite {span} mm, Pfosten auf Gehwegplatten 30 × 30 cm."
        ),
        scale_hint="1:20",
        min_x=-DIM_GAP - 260,
        min_y=-120,
        width=span + 2 * DIM_GAP + 520,
        height=cap + h + SLAB_T + DIM_GAP + 260,
        primitives=prims,
    )


def front_view(g: RaisedBedGeometry) -> Drawing:
    return _elevation(
        g,
        view="front",
        title="Vorderansicht (Längsseite)",
        span=g.p.length_mm,
        end_grain=False,
        posts=_post_x_positions(g),
    )


def side_view(g: RaisedBedGeometry) -> Drawing:
    width = g.p.width_mm
    return _elevation(
        g,
        view="side",
        title="Seitenansicht (Stirnseite)",
        span=width,
        end_grain=True,
        posts=[BOARD_T, width - BOARD_T - POST],
    )


def corner_detail(g: RaisedBedGeometry) -> Drawing:
    size = 320
    inner = BOARD_T + POST
    prims: list[Primitive] = [
        Rect(x=0, y=0, w=size, h=BOARD_T, fill=Fill.WOOD),
        Rect(x=0, y=BOARD_T, w=BOARD_T, h=size - BOARD_T, fill=Fill.WOOD),
        Rect(x=BOARD_T, y=BOARD_T, w=POST, h=POST, fill=Fill.WOOD_END),
        # Screws through the long board into the post and through the short board.
        Line(x1=BOARD_T + 20, y1=-10, x2=BOARD_T + 20, y2=BOARD_T + 32, stroke=Stroke.OUTLINE),
        Line(x1=BOARD_T + 50, y1=-10, x2=BOARD_T + 50, y2=BOARD_T + 32, stroke=Stroke.OUTLINE),
        Line(x1=-10, y1=BOARD_T + 20, x2=BOARD_T + 32, y2=BOARD_T + 20, stroke=Stroke.OUTLINE),
        Line(x1=-10, y1=BOARD_T + 50, x2=BOARD_T + 32, y2=BOARD_T + 50, stroke=Stroke.OUTLINE),
        Dimension(x1=0, y1=0, x2=0, y2=BOARD_T, offset=-70, text=_mm(BOARD_T)),
        Dimension(x1=BOARD_T, y1=0, x2=inner, y2=0, offset=-70, text=_mm(POST)),
        Label(x=inner + 30, y=BOARD_T + 40, text="Pfosten 70 × 70", size="small"),
        Label(x=size - 10, y=-20, text="Längsbrett 28 × 145", anchor="end", size="small"),
        Label(x=BOARD_T + 20, y=size - 10, text="Stirnbrett", size="small"),
        Label(x=inner + 30, y=-35, text="2 × Schraube 5 × 60 A2", size="small"),
    ]
    if g.p.liner:
        offset = 4
        prims += [
            Line(
                x1=size,
                y1=BOARD_T + offset,
                x2=inner + offset,
                y2=BOARD_T + offset,
                stroke=Stroke.MEMBRANE,
            ),
            Line(
                x1=inner + offset,
                y1=BOARD_T + offset,
                x2=inner + offset,
                y2=inner + offset,
                stroke=Stroke.MEMBRANE,
            ),
            Line(
                x1=inner + offset,
                y1=inner + offset,
                x2=BOARD_T + offset,
                y2=inner + offset,
                stroke=Stroke.MEMBRANE,
            ),
            Line(
                x1=BOARD_T + offset,
                y1=inner + offset,
                x2=BOARD_T + offset,
                y2=size,
                stroke=Stroke.MEMBRANE,
            ),
            Label(x=inner + 30, y=inner + 50, text="Noppenbahn", size="small"),
        ]
    return Drawing(
        view="corner_detail",
        title="Eckdetail (Draufsicht)",
        description=(
            "Eckverbindung: Längsbrett läuft durch, Stirnbrett stößt dagegen, beide mit je zwei "
            "Edelstahlschrauben 5 × 60 mm in den innenliegenden Pfosten 70 × 70 mm verschraubt"
            + (", Noppenbahn innen umlaufend." if g.p.liner else ".")
        ),
        scale_hint="1:5",
        min_x=-120,
        min_y=-130,
        width=size + 180,
        height=size + 160,
        primitives=prims,
    )


def build_drawings(g: RaisedBedGeometry) -> list[Drawing]:
    return [plan_view(g), front_view(g), side_view(g), corner_detail(g)]
