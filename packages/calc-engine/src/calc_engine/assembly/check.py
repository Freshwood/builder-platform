"""Deterministic checks of a resolved design against the catalog and basic physics."""

from __future__ import annotations

from dataclasses import dataclass, field

from calc_engine.assembly.geometry import (
    TOUCH_TOL,
    Box,
    Contact,
    analyse,
    bounds_of,
    components,
)
from calc_engine.assembly.resolve import DesignError, ResolvedPart
from calc_engine.catalog import Catalog, CatalogItem
from construction_model.assembly import AssemblyDesign

MAX_EDGE_MM = 4000
MAX_HEIGHT_MM = 2500
DIM_TOL = 0.6
MAX_ERRORS = 12


@dataclass(frozen=True)
class PartInfo:
    part: ResolvedPart
    item: CatalogItem
    kind: str
    """linear, sheet or piece"""
    length_mm: int
    """Cut length (linear), longer side (sheet), 0 for pieces."""
    width_mm: int
    """Shorter side of a sheet part, profile width for linear parts."""
    thickness_mm: int


@dataclass
class CheckedDesign:
    infos: list[PartInfo]
    boxes: list[Box]
    contacts: list[Contact]
    warnings: list[str] = field(default_factory=list)


def _fmt(values: tuple[float, ...]) -> str:
    return " × ".join(f"{v:g}" for v in values)


def _close(a: float, b: float, tol: float = DIM_TOL) -> bool:
    return abs(a - b) <= tol


def classify(part: ResolvedPart, catalog: Catalog) -> PartInfo | str:
    """Match a part to its catalog item; returns an error message if it does not fit."""
    label = f"Bauteil '{part.key}' ({part.name})"
    item = catalog.find(part.material)
    if item is None or not item.designable:
        return f"{label}: unbekanntes Material '{part.material}' (siehe list_materials)"
    dims = part.size
    if min(dims) <= 0:
        return f"{label}: Maße {_fmt(dims)} mm müssen alle größer 0 sein"
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
    for part in parts:
        result = classify(part, catalog)
        if isinstance(result, str):
            errors.append(result)
        else:
            infos.append(result)
    if not parts:
        errors.append("Der Entwurf enthält mit diesen Parametern keine Bauteile")
    if errors:
        raise DesignError(errors[:MAX_ERRORS])

    boxes = [Box(p) for p in parts]
    lo, hi = bounds_of(boxes)
    extent = (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
    if max(extent[0], extent[1]) > MAX_EDGE_MM or extent[2] > MAX_HEIGHT_MM:
        errors.append(
            f"Gesamtmaß {_fmt(tuple(round(e) for e in extent))} mm überschreitet die Grenze für "
            f"freie Entwürfe ({MAX_EDGE_MM} × {MAX_EDGE_MM} × {MAX_HEIGHT_MM} mm). Größere "
            "Bauwerke brauchen eine Fachplanung."
        )
    if lo[2] < -TOUCH_TOL:
        low = [b.part.key for b in boxes if b.bounds()[0][2] < -TOUCH_TOL]
        errors.append(f"Bauteile unter Bodenniveau (z < 0): {', '.join(low[:6])}")

    contacts, collisions = analyse(boxes)
    for c in collisions[:6]:
        a, b = boxes[c.a].part, boxes[c.b].part
        errors.append(
            f"Bauteile '{a.key}' ({a.name}) und '{b.key}' ({b.name}) durchdringen sich "
            f"({_fmt(tuple(round(o, 1) for o in c.overlap))} mm) – Position oder Maß anpassen"
        )

    groups = components(len(boxes), contacts)
    if len(groups) > 1:
        main = max(groups, key=len)
        loose = [boxes[i].part.key for g in groups if g is not main for i in g]
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
    return CheckedDesign(infos=infos, boxes=boxes, contacts=contacts)
