"""Renderer-independent drawing intermediate representation (IR).

Coordinates are millimetres in model space, x to the right, y downwards. Renderers (SVG now,
DXF/PDF later) consume this IR, so all outputs stay dimensionally consistent.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Stroke(StrEnum):
    OUTLINE = "outline"
    THIN = "thin"
    HIDDEN = "hidden"
    CENTER = "center"
    MEMBRANE = "membrane"


class Fill(StrEnum):
    NONE = "none"
    WOOD = "wood"
    WOOD_END = "wood_end"
    STEEL = "steel"
    MEMBRANE = "membrane"
    GROUND = "ground"


class Rect(_Frozen):
    kind: Literal["rect"] = "rect"
    x: float
    y: float
    w: float
    h: float
    stroke: Stroke = Stroke.OUTLINE
    fill: Fill = Fill.NONE
    label: str | None = None


class Line(_Frozen):
    kind: Literal["line"] = "line"
    x1: float
    y1: float
    x2: float
    y2: float
    stroke: Stroke = Stroke.THIN


class Dimension(_Frozen):
    """Linear dimension between two points, drawn ``offset`` mm away from the measured line."""

    kind: Literal["dimension"] = "dimension"
    x1: float
    y1: float
    x2: float
    y2: float
    offset: float
    text: str


class Label(_Frozen):
    kind: Literal["label"] = "label"
    x: float
    y: float
    text: str
    anchor: Literal["start", "middle", "end"] = "start"
    size: Literal["small", "normal"] = "normal"


class Polygon(_Frozen):
    """Filled face of a projected solid. ``tone`` names a material colour, ``shade`` 0..1 its light."""

    kind: Literal["polygon"] = "polygon"
    points: list[tuple[float, float]]
    tone: str
    shade: float = Field(1.0, ge=0, le=1)


class Callout(_Frozen):
    """Position bubble at (bx, by) with a leader line to the target point (x, y)."""

    kind: Literal["callout"] = "callout"
    x: float
    y: float
    bx: float
    by: float
    text: str


Primitive = Annotated[
    Rect | Line | Dimension | Label | Polygon | Callout, Field(discriminator="kind")
]


class LegendEntry(_Frozen):
    tone: str
    label: str


class Drawing(_Frozen):
    view: str
    title: str
    description: str
    scale_hint: str
    min_x: float
    min_y: float
    width: float
    height: float
    primitives: list[Primitive]
    legend: list[LegendEntry] = Field(default_factory=list)
