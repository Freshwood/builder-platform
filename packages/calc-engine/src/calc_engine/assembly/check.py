"""Deterministic checks of a resolved design against the catalog and basic physics."""

from __future__ import annotations

from dataclasses import dataclass, field

from calc_engine.assembly.geometry import (
    TOUCH_TOL,
    Box,
    Contact,
    GeometryError,
    Overlap,
    analyse,
    bounds_of,
    components,
)
from calc_engine.assembly.resolve import DesignError, ResolvedPart
from calc_engine.assembly.shapes import ShapeError
from calc_engine.catalog import LUMBER_PREFIX, Catalog, CatalogItem
from construction_model.assembly import AssemblyDesign

MAX_EDGE_MM = 4000
MAX_HEIGHT_MM = 2500
# Buildings (category "building"): houses, sheds, garages with foundation, frame and roof.
MAX_EDGE_BUILDING_MM = 25000
MAX_HEIGHT_BUILDING_MM = 15000
DIM_TOL = 0.6
MAX_ERRORS = 12


@dataclass(frozen=True)
class PartInfo:
    part: ResolvedPart
    item: CatalogItem
    kind: str
    """linear, sheet, piece or bulk"""
    length_mm: int
    """Cut length (linear), longer side (sheet), 0 for pieces."""
    width_mm: int
    """Shorter side of a sheet part, profile width for linear parts."""
    thickness_mm: int
    signature: str = ""
    """Shape, cutouts and end cuts; parts only share a position if this matches, too."""
    quantity: float = 0.0
    """Bulk: m² (area basis) or m³ (volume basis)."""


@dataclass
class CheckedDesign:
    infos: list[PartInfo]
    boxes: list[Box]
    contacts: list[Contact]
    overlaps: list[Overlap] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _fmt(values: tuple[float, ...]) -> str:
    return " × ".join(f"{v:g}" for v in values)


def _close(a: float, b: float, tol: float = DIM_TOL) -> bool:
    return abs(a - b) <= tol


def _label(part: ResolvedPart) -> str:
    return f"Bauteil '{part.key}' ({part.name})"


def _section(part: ResolvedPart, catalog: Catalog) -> tuple[float, float] | None:
    """Cross-section of a member: explicit, from a lumber id or from a catalog profile."""
    if part.section is not None:
        return part.section
    item = catalog.find(part.material)
    if item is not None and item.section_mm:
        return (float(item.section_mm[0]), float(item.section_mm[1]))
    return None


def build_solid(part: ResolvedPart, catalog: Catalog) -> Box | str:
    """The part's solid, or an error message (bad shape, cut or cross-section)."""
    try:
        if part.is_member:
            section = _section(part, catalog)
            if section is None:
                return (
                    f"{_label(part)}: Querschnitt fehlt – section angeben oder Material mit "
                    "Querschnitt wählen (z. B. lumber_oak_beam_160x160)"
                )
            box = Box(part, section)
        else:
            if min(part.size) <= 0:
                return f"{_label(part)}: Maße {_fmt(part.size)} mm müssen alle größer 0 sein"
            box = Box(part)
        _ = box.pieces
    except (GeometryError, ShapeError) as exc:
        return f"{_label(part)}: {exc}"
    return box


def _signature(part: ResolvedPart) -> str:
    bits: list[str] = []
    if part.shape is not None and part.shape.kind != "rect":
        bits.append(repr(part.shape))
    if part.cutouts:
        bits.append(repr(part.cutouts))
    if part.cuts != ("square", "square"):
        bits.append("/".join(part.cuts))
    return "|".join(bits)


def classify(part: ResolvedPart, catalog: Catalog, box: Box | None = None) -> PartInfo | str:
    """Match a part to its catalog item; returns an error message if it does not fit."""
    label = _label(part)
    if box is None:
        built = build_solid(part, catalog)
        if isinstance(built, str):
            return built
        box = built
    item: CatalogItem | None
    dims = box.dims if part.is_member else part.size
    if part.material.startswith(LUMBER_PREFIX):
        lumber = catalog.resolve_lumber(part.material, dims)
        if isinstance(lumber, str):
            return f"{label}: {lumber}"
        item = lumber
    else:
        item = catalog.find(part.material)
    if item is None or not item.designable:
        return f"{label}: unbekanntes Material '{part.material}' (siehe list_materials)"
    if min(dims) <= 0:
        return f"{label}: Maße {_fmt(dims)} mm müssen alle größer 0 sein"
    info = _classify_item(part, item, dims, box, label)
    if isinstance(info, PartInfo):
        if part.shape is not None and part.shape.kind != "rect" and info.kind == "piece":
            return f"{label}: Fertigteile haben feste Form – keine shape angeben"
        return PartInfo(
            info.part,
            info.item,
            info.kind,
            info.length_mm,
            info.width_mm,
            info.thickness_mm,
            _signature(part),
            info.quantity,
        )
    return info


def _classify_item(
    part: ResolvedPart,
    item: CatalogItem,
    dims: tuple[float, float, float],
    box: Box,
    label: str,
) -> PartInfo | str:
    if item.kind == "bulk":
        t = box.lw
        lo, hi = item.thickness_range_mm or (1, 100000)
        if not lo - DIM_TOL <= t <= hi + DIM_TOL:
            return (
                f"{label}: Stärke {t:g} mm passt nicht zu '{item.id}' ({lo}–{hi} mm; Stärke = "
                "kleinstes Maß bzw. Stabdicke)"
            )
        if item.bulk_basis == "area":
            quantity = box.face_area_mm2 / 1e6
        else:
            quantity = box.volume_mm3 / 1e9
        if part.is_member:
            length, width = box.dims[2], box.lv
        else:
            length, width = sorted((box.lu, box.lv), reverse=True)
        return PartInfo(
            part, item, "bulk", round(length), round(width), round(t), quantity=quantity
        )
    if item.kind == "linear" and item.section_mm:
        t, w = sorted(item.section_mm)
        for k in range(3):
            rest = sorted(dims[j] for j in range(3) if j != k)
            if _close(rest[0], t) and _close(rest[1], w):
                length = round(dims[k])
                longest = max(item.stock_lengths_mm)
                if length > longest:
                    return (
                        f"{label}: Länge {length} mm überschreitet die längste Handelslänge "
                        f"{longest} mm von '{item.id}' – teilen oder anderes Material wählen"
                    )
                if length < 20:
                    return f"{label}: Länge {length} mm ist zu kurz"
                return PartInfo(part, item, "linear", length, w, t)
        return (
            f"{label}: Maße {_fmt(dims)} mm passen nicht zum Querschnitt "
            f"{t} × {w} mm von '{item.id}' (zwei Maße müssen dem Querschnitt entsprechen)"
        )
    if item.kind == "sheet" and item.thickness_mm and item.sheet_mm:
        for k in range(3):
            if _close(dims[k], item.thickness_mm):
                rest = sorted((dims[j] for j in range(3) if j != k), reverse=True)
                sheet = sorted(item.sheet_mm, reverse=True)
                if rest[0] > sheet[0] or rest[1] > sheet[1]:
                    return (
                        f"{label}: Zuschnitt {_fmt(tuple(rest))} mm ist größer als das "
                        f"Plattenformat {_fmt(tuple(float(s) for s in sheet))} mm"
                    )
                return PartInfo(
                    part, item, "sheet", round(rest[0]), round(rest[1]), item.thickness_mm
                )
        return (
            f"{label}: kein Maß von {_fmt(dims)} mm entspricht der Plattenstärke "
            f"{item.thickness_mm} mm von '{item.id}'"
        )
    if item.kind == "piece" and item.size_mm:
        if all(_close(a, b, 1.0) for a, b in zip(sorted(dims), sorted(item.size_mm), strict=True)):
            return PartInfo(part, item, "piece", 0, 0, 0)
        return f"{label}: '{item.id}' hat die feste Größe {_fmt(tuple(float(s) for s in item.size_mm))} mm"
    return f"{label}: '{item.id}' ist kein platzierbares Bauteil – unter hardware angeben"


def check_design(
    design: AssemblyDesign, parts: list[ResolvedPart], catalog: Catalog
) -> CheckedDesign:
    errors: list[str] = []
    infos: list[PartInfo] = []
    boxes: list[Box] = []
    for part in parts:
        box = build_solid(part, catalog)
        result = box if isinstance(box, str) else classify(part, catalog, box)
        if isinstance(result, str):
            errors.append(result)
        else:
            assert isinstance(box, Box)
            infos.append(result)
            boxes.append(box)
    if not parts:
        errors.append("Der Entwurf enthält mit diesen Parametern keine Bauteile")
    if errors:
        raise DesignError(errors[:MAX_ERRORS])

    building = design.category == "building"
    max_edge = MAX_EDGE_BUILDING_MM if building else MAX_EDGE_MM
    max_height = MAX_HEIGHT_BUILDING_MM if building else MAX_HEIGHT_MM
    lo, hi = bounds_of(boxes)
    extent = (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
    if max(extent[0], extent[1]) > max_edge or extent[2] > max_height:
        errors.append(
            f"Gesamtmaß {_fmt(tuple(round(e) for e in extent))} mm überschreitet die Grenze "
            f"({max_edge} × {max_edge} × {max_height} mm)"
            + ("" if building else '; Häuser und Hütten als category="building" planen')
        )
    # Buildings may reach into the ground with their foundations (concrete) only.
    low = [
        b.part.key
        for b, info in zip(boxes, infos, strict=True)
        if b.bounds()[0][2] < -TOUCH_TOL and not (building and info.item.material == "concrete")
    ]
    if low:
        errors.append(
            f"Bauteile unter Bodenniveau (z < 0): {', '.join(low[:6])}"
            + (" – im Erdreich nur Fundamente aus Beton" if building else "")
        )

    joined = _joined_pairs(design, boxes)
    contacts, collisions, overlaps = analyse(
        boxes, lambda i, j: joined.get(_pair(boxes, i, j)) in {"half_lap", "notch"}
    )
    for c in collisions[:6]:
        a, b = boxes[c.a].part, boxes[c.b].part
        errors.append(
            f"Bauteile '{a.key}' ({a.name}) und '{b.key}' ({b.name}) durchdringen sich "
            f"({_fmt(tuple(round(o, 1) for o in c.overlap))} mm) – Position oder Maß anpassen"
            " oder als Holzverbindung (joints: half_lap/notch) angeben"
        )
    errors.extend(_check_joints(design, boxes, contacts, overlaps))

    groups = components(len(boxes), contacts)
    main = max(groups, key=len)
    wall_y = hi[1] - TOUCH_TOL
    loose = [
        boxes[i].part.key
        for g in groups
        if g is not main
        # Separate groups are fine on a wall (e.g. two shutter wings) if each is fixed to it.
        and not (design.support == "wall" and any(boxes[j].bounds()[1][1] >= wall_y for j in g))
        for i in g
    ]
    if loose:
        errors.append(
            "Nicht alle Bauteile sind verbunden (keine Kontaktfläche): "
            f"{', '.join(loose[:8])}{' …' if len(loose) > 8 else ''}"
        )

    if design.support == "floor":
        if not any(b.bounds()[0][2] <= TOUCH_TOL for b in boxes):
            errors.append("Kein Bauteil steht auf dem Boden (z = 0)")
    elif not any(b.bounds()[1][1] >= hi[1] - TOUCH_TOL for b in boxes):
        errors.append("Kein Bauteil liegt an der Wand (größtes y) an")

    if errors:
        raise DesignError(errors[:MAX_ERRORS])
    return CheckedDesign(infos=infos, boxes=boxes, contacts=contacts, overlaps=overlaps)


def _pair(boxes: list[Box], i: int, j: int) -> frozenset[str]:
    return frozenset((boxes[i].part.spec_id, boxes[j].part.spec_id))


def _joined_pairs(design: AssemblyDesign, boxes: list[Box]) -> dict[frozenset[str], str]:
    return {frozenset((j.part, j.into)): j.kind for j in design.joints}


def notch_depth(part: Box, points: list[tuple[float, float, float]]) -> float:
    """How deep an overlap reaches into ``part`` across its width (seat cut, lap)."""
    if not points:
        return 0.0
    f = part.frame
    across = f.v if part.lv <= part.lu else f.u
    if part.part.is_member:
        across = f.v
    values = [sum(p[k] * across[k] for k in range(3)) for p in points]
    return max(values) - min(values)


def _check_joints(
    design: AssemblyDesign,
    boxes: list[Box],
    contacts: list[Contact],
    overlaps: list[Overlap],
) -> list[str]:
    errors: list[str] = []
    linked = {frozenset((c.a, c.b)) for c in contacts}
    for joint in design.joints:
        pairs = [
            (i, j)
            for i, b in enumerate(boxes)
            if b.part.spec_id == joint.part
            for j, c in enumerate(boxes)
            if c.part.spec_id == joint.into and i != j and frozenset((i, j)) in linked
        ]
        if not pairs:
            errors.append(
                f"Holzverbindung {joint.kind} '{joint.part}' → '{joint.into}': die Teile "
                "berühren sich nirgends"
            )
            continue
        if joint.kind != "notch":
            continue
        for ov in overlaps:
            for i, j in pairs:
                if frozenset((i, j)) != frozenset((ov.a, ov.b)):
                    continue
                part = boxes[i]
                depth = notch_depth(part, ov.points)
                limit = part.lv / 3 if part.part.is_member else min(part.lu, part.lv) / 3
                if depth > limit + TOUCH_TOL:
                    errors.append(
                        f"Kerve von '{part.part.key}' ist {depth:.0f} mm tief, höchstens "
                        f"{limit:.0f} mm (1/3 der Höhe) – Bauteil höher setzen"
                    )
                    return errors
    return errors
