"""Render the drawing IR to accessible, deterministic SVG.

The output is byte-stable for identical input (golden-file tests) and carries ``<title>`` and
``<desc>`` for screen readers (WCAG 2.2 / BFSG).
"""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from construction_model.drawing import (
    Callout,
    Dimension,
    Drawing,
    Fill,
    Label,
    Line,
    Polygon,
    Rect,
    Stroke,
)

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
# Base colours of material tones (free-form designs); faces are darkened by their light value.
TONES: dict[str, str] = {
    "spruce": "#ecd3a2",
    "douglas": "#dba06e",
    "larch": "#e3b27a",
    "plywood": "#efd9b0",
    "glulam": "#f2d396",
    "osb": "#d6b26f",
    "mdf": "#b8a48a",
    "hdf": "#d4cfc6",
    "steel": "#9ca3af",
    "rubber": "#4b5563",
    "concrete": "#bdbab4",
}
CALLOUT_R = 9.0
LEGEND_ROW = 22.0


def tone_color(tone: str, shade: float = 1.0) -> str:
    base = TONES.get(tone, "#d1d5db")
    r, g, b = (int(base[i : i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{max(0, min(255, round(c * shade))):02x}" for c in (r, g, b))


def _n(value: float) -> str:
    """Format a number compactly and deterministically."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


class _Canvas:
    def __init__(self, drawing: Drawing, max_width_px: float, max_height_px: float) -> None:
        self.d = drawing
        self.scale = min(max_width_px / drawing.width, max_height_px / drawing.height)
        self.width_px = drawing.width * self.scale
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


def _polygon(c: _Canvas, poly: Polygon) -> str:
    points = " ".join(f"{c.x(x)},{c.y(y)}" for x, y in poly.points)
    return (
        f'<polygon points="{points}" fill="{tone_color(poly.tone, poly.shade)}" '
        'stroke="#374151" stroke-width="0.6" stroke-linejoin="round"/>'
    )


def _callout(c: _Canvas, call: Callout) -> str:
    tx, ty, bx, by = (
        float(c.x(call.x)),
        float(c.y(call.y)),
        float(c.x(call.bx)),
        float(c.y(call.by)),
    )
    dist = max(((tx - bx) ** 2 + (ty - by) ** 2) ** 0.5, 1e-6)
    ex, ey = bx + (tx - bx) / dist * CALLOUT_R, by + (ty - by) / dist * CALLOUT_R
    return (
        f'<line x1="{_n(ex)}" y1="{_n(ey)}" x2="{_n(tx)}" y2="{_n(ty)}" stroke="#1f2937" '
        'stroke-width="0.8"/>'
        f'<circle cx="{_n(tx)}" cy="{_n(ty)}" r="1.8" fill="#1f2937"/>'
        f'<circle cx="{_n(bx)}" cy="{_n(by)}" r="{_n(CALLOUT_R)}" fill="#ffffff" '
        'stroke="#1f2937" stroke-width="1.2"/>'
        f'<text x="{_n(bx)}" y="{_n(by + 3.6)}" font-size="10" font-weight="700" {FONT} '
        f'fill="#111827" text-anchor="middle">{escape(call.text)}</text>'
    )


def _legend(drawing: Drawing, width_px: float, top: float) -> tuple[str, float]:
    """Material legend below the drawing; returns markup and its height."""
    if not drawing.legend:
        return "", 0.0
    parts: list[str] = []
    x, y = 10.0, top + 8
    for entry in drawing.legend:
        item_width = 22 + 6.5 * len(entry.label) + 18
        if x + item_width > width_px - 10 and x > 10:
            x, y = 10.0, y + LEGEND_ROW
        parts.append(
            f'<rect x="{_n(x)}" y="{_n(y)}" width="14" height="14" rx="2" '
            f'fill="{tone_color(entry.tone, 0.9)}" stroke="#374151" stroke-width="0.6"/>'
            f'<text x="{_n(x + 20)}" y="{_n(y + 11)}" font-size="11" {FONT} fill="#111827">'
            f"{escape(entry.label)}</text>"
        )
        x += item_width
    return "".join(parts), y + LEGEND_ROW - top + 16


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


def render_svg(
    drawing: Drawing,
    *,
    max_width_px: float = 760,
    max_height_px: float | None = None,
    element_id: str = "drawing",
) -> str:
    """Render a drawing; tall drawings are limited to ``max_height_px`` (default: square)."""
    c = _Canvas(drawing, max_width_px, max_height_px or max_width_px)
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
            case Polygon():
                body.append(_polygon(c, prim))
            case Callout():
                body.append(_callout(c, prim))
    legend, legend_height = _legend(drawing, c.width_px, c.height_px)
    total_height = c.height_px + legend_height
    title_id, desc_id = f"{element_id}-title", f"{element_id}-desc"
    width, height = _n(c.width_px), _n(total_height)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" '
        f"aria-labelledby={quoteattr(f'{title_id} {desc_id}')}>"
        f'<title id="{title_id}">{escape(drawing.title)}</title>'
        f'<desc id="{desc_id}">{escape(drawing.description)}</desc>'
        f"{DEFS.replace('{eid}', element_id)}"
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>'
        f"{''.join(body)}"
        f"{legend}"
        f'<text x="{_n(c.width_px - 8)}" y="{_n(total_height - 8)}" font-size="10" {FONT} '
        f'fill="#6b7280" text-anchor="end">{escape(drawing.title)} · Maße in mm · '
        "Darstellung nicht maßstäblich</text>"
        "</svg>\n"
    )
