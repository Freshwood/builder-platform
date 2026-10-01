"""Render the drawing IR to accessible, deterministic SVG.

The output is byte-stable for identical input (golden-file tests) and carries ``<title>`` and
``<desc>`` for screen readers (WCAG 2.2 / BFSG).
"""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from construction_model.drawing import Dimension, Drawing, Fill, Label, Line, Rect, Stroke

STROKES: dict[Stroke, str] = {
    Stroke.OUTLINE: 'stroke="#1f2937" stroke-width="1.4"',
    Stroke.THIN: 'stroke="#4b5563" stroke-width="0.7"',
    Stroke.HIDDEN: 'stroke="#6b7280" stroke-width="0.8" stroke-dasharray="5 3"',
    Stroke.CENTER: 'stroke="#b45309" stroke-width="0.9" stroke-dasharray="12 3 2 3"',
    Stroke.MEMBRANE: 'stroke="#2563eb" stroke-width="1.6" stroke-dasharray="3 2"',
}
FILLS: dict[Fill, str] = {
    Fill.NONE: "none",
    Fill.WOOD: "#ecd3a8",
    Fill.WOOD_END: "url(#{eid}-end-grain)",
    Fill.STEEL: "#9ca3af",
    Fill.MEMBRANE: "#bfdbfe",
    Fill.GROUND: "#d6d3d1",
}
DEFS = (
    "<defs>"
    '<pattern id="{eid}-end-grain" width="6" height="6" patternUnits="userSpaceOnUse" '
    'patternTransform="rotate(45)">'
    '<rect width="6" height="6" fill="#dcb98a"/>'
    '<line x1="0" y1="0" x2="0" y2="6" stroke="#8b5e34" stroke-width="1"/>'
    "</pattern>"
    "</defs>"
)
FONT = 'font-family="Inter, Helvetica, Arial, sans-serif"'
TICK = 4.0


def _n(value: float) -> str:
    """Format a number compactly and deterministically."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


class _Canvas:
    def __init__(self, drawing: Drawing, max_width_px: float) -> None:
        self.d = drawing
        self.scale = max_width_px / drawing.width
        self.width_px = max_width_px
        self.height_px = drawing.height * self.scale

    def x(self, value: float) -> str:
        return _n((value - self.d.min_x) * self.scale)

    def y(self, value: float) -> str:
        return _n((value - self.d.min_y) * self.scale)

    def length(self, value: float) -> str:
        return _n(value * self.scale)


def _rect(c: _Canvas, r: Rect, eid: str) -> str:
    fill = FILLS[r.fill].replace("{eid}", eid)
    return (
        f'<rect x="{c.x(r.x)}" y="{c.y(r.y)}" width="{c.length(r.w)}" height="{c.length(r.h)}" '
        f'fill="{fill}" {STROKES[r.stroke]}/>'
    )


def _line(c: _Canvas, line: Line) -> str:
    return (
        f'<line x1="{c.x(line.x1)}" y1="{c.y(line.y1)}" x2="{c.x(line.x2)}" '
        f'y2="{c.y(line.y2)}" {STROKES[line.stroke]}/>'
    )


def _label(c: _Canvas, label: Label) -> str:
    size = "10" if label.size == "small" else "12"
    return (
        f'<text x="{c.x(label.x)}" y="{c.y(label.y)}" font-size="{size}" {FONT} '
        f'fill="#111827" text-anchor="{label.anchor}">{escape(label.text)}</text>'
    )


def _dimension(c: _Canvas, dim: Dimension) -> str:
    horizontal = abs(dim.x2 - dim.x1) >= abs(dim.y2 - dim.y1)
    style = STROKES[Stroke.THIN]
    if horizontal:
        y = dim.y1 + dim.offset
        x1, x2 = sorted((dim.x1, dim.x2))
        sx1, sx2, sy = float(c.x(x1)), float(c.x(x2)), float(c.y(y))
        parts = [
            f'<line x1="{c.x(x1)}" y1="{c.y(dim.y1)}" x2="{c.x(x1)}" y2="{_n(sy + TICK)}" {style}/>',
            f'<line x1="{c.x(x2)}" y1="{c.y(dim.y2)}" x2="{c.x(x2)}" y2="{_n(sy + TICK)}" {style}/>',
            f'<line x1="{_n(sx1)}" y1="{_n(sy)}" x2="{_n(sx2)}" y2="{_n(sy)}" {style}/>',
        ]
        for sx in (sx1, sx2):
            parts.append(
                f'<line x1="{_n(sx - TICK)}" y1="{_n(sy + TICK)}" x2="{_n(sx + TICK)}" '
                f'y2="{_n(sy - TICK)}" {STROKES[Stroke.OUTLINE]}/>'
            )
        parts.append(
            f'<text x="{_n((sx1 + sx2) / 2)}" y="{_n(sy - 4)}" font-size="11" {FONT} '
            f'fill="#111827" text-anchor="middle">{escape(dim.text)}</text>'
        )
    else:
        x = dim.x1 + dim.offset
        y1, y2 = sorted((dim.y1, dim.y2))
        sy1, sy2, sx = float(c.y(y1)), float(c.y(y2)), float(c.x(x))
        sign = 1 if dim.offset >= 0 else -1
        parts = [
            f'<line x1="{c.x(dim.x1)}" y1="{c.y(y1)}" x2="{_n(sx + sign * TICK)}" y2="{c.y(y1)}" {style}/>',
            f'<line x1="{c.x(dim.x2)}" y1="{c.y(y2)}" x2="{_n(sx + sign * TICK)}" y2="{c.y(y2)}" {style}/>',
            f'<line x1="{_n(sx)}" y1="{_n(sy1)}" x2="{_n(sx)}" y2="{_n(sy2)}" {style}/>',
        ]
        for sy in (sy1, sy2):
            parts.append(
                f'<line x1="{_n(sx - TICK)}" y1="{_n(sy + TICK)}" x2="{_n(sx + TICK)}" '
                f'y2="{_n(sy - TICK)}" {STROKES[Stroke.OUTLINE]}/>'
            )
        tx, ty = _n(sx - 4), _n((sy1 + sy2) / 2)
        parts.append(
            f'<text x="{tx}" y="{ty}" font-size="11" {FONT} fill="#111827" '
            f'text-anchor="middle" transform="rotate(-90 {tx} {ty})">{escape(dim.text)}</text>'
        )
    return "".join(parts)


def render_svg(drawing: Drawing, *, max_width_px: float = 760, element_id: str = "drawing") -> str:
    c = _Canvas(drawing, max_width_px)
    body: list[str] = []
    for prim in drawing.primitives:
        match prim:
            case Rect():
                body.append(_rect(c, prim, element_id))
            case Line():
                body.append(_line(c, prim))
            case Dimension():
                body.append(_dimension(c, prim))
            case Label():
                body.append(_label(c, prim))
    title_id, desc_id = f"{element_id}-title", f"{element_id}-desc"
    width, height = _n(c.width_px), _n(c.height_px)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" '
        f"aria-labelledby={quoteattr(f'{title_id} {desc_id}')}>"
        f'<title id="{title_id}">{escape(drawing.title)}</title>'
        f'<desc id="{desc_id}">{escape(drawing.description)}</desc>'
        f"{DEFS.replace('{eid}', element_id)}"
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>'
        f"{''.join(body)}"
        f'<text x="{_n(c.width_px - 8)}" y="{_n(c.height_px - 8)}" font-size="10" {FONT} '
        f'fill="#6b7280" text-anchor="end">{escape(drawing.title)} · Maße in mm · '
        "Darstellung nicht maßstäblich</text>"
        "</svg>\n"
    )
