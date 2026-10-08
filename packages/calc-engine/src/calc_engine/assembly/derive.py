"""Derive BOM, cut list, costs, instructions and notices from a checked design (ADR-0004)."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from calc_engine.assembly.check import CheckedDesign, PartInfo, check_design
from calc_engine.assembly.geometry import TOUCH_TOL, Box, Contact, bounds_of
from calc_engine.assembly.joints import JointPlan, JointWork, member_angle, plan_joints
from calc_engine.assembly.projection import MAX_TEMPLATES, build_drawings, build_template
from calc_engine.assembly.resolve import (
    DesignError,
    is_included,
    resolve_parts,
    resolve_quantity,
    substitute,
)
from calc_engine.assembly.sheets import plan_sheets
from calc_engine.catalog import BomBuilder, Catalog, CatalogItem, money, sum_money
from calc_engine.cutting import plan_cuts
from calc_engine.pack import PackBuild
from construction_model.assembly import AssemblyDesign
from construction_model.model import (
    BomLine,
    Component,
    CostSummary,
    CutLine,
    InstructionStep,
    Notice,
    Origin,
    ParamValue,
    Profile,
    RuleRef,
    Severity,
    Solid,
    SolidMesh,
    SolidRotation,
    StockPlan,
    Tool,
)

DESIGN_PACK_ID = "design"
DESIGN_PACK_VERSION = "1.1.0"
_GUID_NS = uuid5(NAMESPACE_URL, "https://homeworking.example/packs/design")
SCREW_SPACING_MM = 250
SCREW_RESERVE = Decimal("1.1")
FINISH_COATS = 2
JOINTS_PER_GLUE = 60
TIP_RATIO = 2.5
TIP_MIN_HEIGHT = 900
LUMBER_NOTE = "Maßholz: im Holzfachhandel/Hobelwerk in diesem Querschnitt bestellen"
BULK_RESERVE = Decimal("1.05")
# Hardware that building steps talk about must also be in the BOM (FD-HW).
_HARDWARE_MENTIONS: dict[str, tuple[re.Pattern[str], str]] = {
    "hinge": (
        re.compile(r"scharnier|kreuzgeh[äa]nge|ladenband|türband|topfband", re.IGNORECASE),
        "Scharniere/Bänder",
    ),
    "latch": (
        re.compile(
            r"verschluss|schubriegel|kantriegel|sturmhaken|ladenhaken|überwurf|schnäpper",
            re.IGNORECASE,
        ),
        "einen Verschluss",
    ),
    "handle": (re.compile(r"\bgriff|\bknauf", re.IGNORECASE), "Griffe"),
}

RULES: dict[str, RuleRef] = {
    r.id: r
    for r in [
        RuleRef(
            id="FD-MAT",
            version="1",
            title="Querschnitte, Plattenstärken und Längen nur aus dem Katalog",
        ),
        RuleRef(
            id="FD-COLL", version="1", title="Keine Durchdringung von Bauteilen (Toleranz 1 mm)"
        ),
        RuleRef(
            id="FD-CONN",
            version="1",
            title="Alle Bauteile zusammenhängend, Boden- bzw. Wandkontakt",
        ),
        RuleRef(
            id="FD-SIZE",
            version="2",
            title="Objekte max. 4 × 4 m Grundfläche, 2,5 m Höhe; Gebäude max. 25 × 25 m, 15 m Höhe",
        ),
        RuleRef(
            id="FD-SHAPE",
            version="1",
            title="Konturen (Wolke, Ellipse, Giebel, Bogen, Polygon) und Ausschnitte aus dem Rohteil; Schablone je Position",
        ),
        RuleRef(
            id="FD-JOINT",
            version="1",
            title="Zapfen: Stärke 1/3 Holz, Länge 0,4 × Gegenholz (30–60 mm), Holznagel je Zapfen; Blatt: halbe Überdeckung; Kerve: höchstens 1/3 der Höhe",
        ),
        RuleRef(
            id="FD-BULK",
            version="1",
            title="Ausfachung, Dämmung, Beton nach Volumen, Dachdeckung und Schalung nach Fläche, +5 % Verschnitt",
        ),
        RuleRef(
            id="FD-BUILD",
            version="1",
            title="Gebäude: Statik, Gründung und Baugenehmigung durch Fachplaner; Engine prüft nur Geometrie und Mengen",
        ),
        RuleRef(
            id="FD-SCREW",
            version="1",
            title="Je Kontaktfläche ≥ 2 Schrauben, je 250 mm Kontaktlänge eine weitere; Länge ≈ 2 × Bauteilstärke",
        ),
        RuleRef(
            id="FD-CUT",
            version="1",
            title="Stangen: günstigste Handelslänge, First-Fit-Decreasing, Schnittfuge 4 mm",
        ),
        RuleRef(id="FD-SHEET", version="1", title="Platten: Regal-Heuristik, Schnittfuge 4 mm"),
        RuleRef(
            id="FD-TIP", version="1", title="Kippsicherung ab Höhe ≥ 900 mm und Höhe/Tiefe > 2,5"
        ),
        RuleRef(id="FD-FINISH", version="1", title="Oberfläche: 2 Anstriche auf alle Holzflächen"),
        RuleRef(
            id="FD-LUMBER",
            version="1",
            title="Maßholz: jede Holzart in jedem Querschnitt, Preis aus Holzvolumen × Preis je m³",
        ),
        RuleRef(
            id="FD-HW",
            version="1",
            title="In Bauschritten genannte Beschläge (Scharniere, Verschlüsse, Griffe) sind platziert oder in der Stückliste",
        ),
    ]
}


@dataclass(frozen=True)
class Position:
    number: int
    spec_id: str
    name: str
    info: PartInfo


def _guid(key: str) -> UUID:
    return uuid5(_GUID_NS, key)


def _m(mm: float) -> str:
    return f"{mm / 1000:.2f}".replace(".", ",") + " m"


def _positions(infos: list[PartInfo]) -> tuple[list[Position], list[int]]:
    """Group identical parts into numbered positions; returns positions and per-part numbers."""
    keys: dict[tuple[object, ...], int] = {}
    positions: list[Position] = []
    numbers: list[int] = []
    for info in infos:
        key = (info.part.name, info.item.id, info.length_mm, info.width_mm, info.signature)
        if key not in keys:
            keys[key] = len(positions) + 1
            positions.append(Position(keys[key], info.part.spec_id, info.part.name, info))
        numbers.append(keys[key])
    return positions, numbers


def _cut_note(box: Box, extra_mm: int) -> str | None:
    """How a part differs from a straight saw cut (contour, holes, angled ends, tenons)."""
    notes: list[str] = []
    if box.shaped:
        notes.append("Kontur nach Schablone aussägen")
    if box.holes:
        notes.append(f"{len(box.holes)} Ausschnitt(e)")
    angle = member_angle(box)
    if angle is not None and box.part.cuts != ("square", "square"):
        labels = {
            "level": "Waagschnitt",
            "plumb": "Lotschnitt",
            "corner": "Klaue",
            "square": "gerade",
        }
        ends = " / ".join(labels[c] for c in box.part.cuts)
        notes.append(f"Enden {ends}, Neigung {angle:.1f}°".replace(".", ","))
    if extra_mm:
        notes.append(f"inkl. {extra_mm} mm Zapfen")
    return "; ".join(notes) or None


def _cut_list(
    positions: list[Position], numbers: list[int], checked: CheckedDesign, plan: JointPlan
) -> list[CutLine]:
    counts: dict[int, int] = defaultdict(int)
    first: dict[int, int] = {}
    for i, n in enumerate(numbers):
        counts[n] += 1
        first.setdefault(n, i)
    lines: list[CutLine] = []
    for pos in positions:
        info = pos.info
        if info.kind in {"piece", "bulk"}:
            continue
        i = first[pos.number]
        note = _cut_note(checked.boxes[i], plan.extra_mm.get(i, 0))
        if info.kind == "linear":
            section = f"{info.thickness_mm} × {info.width_mm}"
            lines.append(
                CutLine(
                    part=pos.name,
                    material=info.item.name,
                    cross_section=section,
                    length_mm=info.length_mm,
                    count=counts[pos.number],
                    position=pos.number,
                    note=note,
                )
            )
        else:
            lines.append(
                CutLine(
                    part=pos.name,
                    material=info.item.name,
                    cross_section=f"{info.thickness_mm} mm Platte",
                    length_mm=info.length_mm,
                    width_mm=info.width_mm,
                    count=counts[pos.number],
                    position=pos.number,
                    note=note,
                )
            )
    return lines


def _linear_stock(item: CatalogItem, pieces: list[int], bom: BomBuilder) -> StockPlan:
    best: tuple[Decimal, int, int, list[list[int]]] | None = None
    for stock in sorted(item.stock_lengths_mm):
        if stock < max(pieces):
            continue
        bars = plan_cuts(pieces, stock)
        cost = (item.price_min + item.price_max) * stock * len(bars)
        candidate = (cost, len(bars), stock, [list(b.pieces) for b in bars])
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    assert best is not None
    _, count, stock, layout = best
    per_m_min, per_m_max = item.price_min, item.price_max
    factor = Decimal(stock) / 1000
    bom.add_custom(
        f"{item.id}@{stock}",
        item.name,
        f"{item.spec}, Länge {_m(stock)}",
        count,
        "Stk",
        per_m_min * factor,
        per_m_max * factor,
        note=LUMBER_NOTE if item.made_to_order else None,
    )
    waste = sum(stock - sum(bar) - 4 * max(0, len(bar) - 1) for bar in layout)
    return StockPlan(
        item_id=f"{item.id}@{stock}",
        stock_length_mm=stock,
        stock_count=count,
        waste_mm=waste,
        name=f"{item.name} {item.spec}",
        bars=layout,
        utilization_pct=round(100 * (count * stock - waste) / (count * stock)),
    )


def _sheet_stock(item: CatalogItem, pieces: list[tuple[int, int]], bom: BomBuilder) -> StockPlan:
    assert item.sheet_mm is not None
    sheets = plan_sheets(pieces, item.sheet_mm)
    area = item.sheet_mm[0] * item.sheet_mm[1]
    used = sum(s.used_area for s in sheets)
    bom.add(item.id, len(sheets), note="Zuschnitt im Baumarkt möglich, siehe Zuschnittliste")
    return StockPlan(
        item_id=item.id,
        stock_length_mm=max(item.sheet_mm),
        stock_count=len(sheets),
        waste_mm=0,
        name=f"{item.name} {item.spec}",
        utilization_pct=round(100 * used / (area * len(sheets))),
    )


def _screw_for(thickness: float, cap: float, screws: list[CatalogItem]) -> CatalogItem:
    """Shortest screw of at least ~2 × thickness that does not pierce both parts."""
    needed = thickness + max(24.0, thickness)
    by_length = sorted(screws, key=lambda s: s.screw_length_mm or 0)
    fitting = [s for s in by_length if (s.screw_length_mm or 0) <= cap]
    for screw in fitting:
        if (screw.screw_length_mm or 0) >= needed:
            return screw
    return fitting[-1] if fitting else by_length[0]


@dataclass(frozen=True)
class Joint:
    """A screwed contact: ``through`` is screwed into ``into`` with ``count`` screws."""

    through: int
    into: int
    screw: CatalogItem
    count: int
    axis: int | None


def _screws(
    checked: CheckedDesign, outdoor: bool, catalog: Catalog, skip: set[frozenset[int]]
) -> tuple[list[Joint], bool]:
    screws = [i for i in catalog.items if i.kind == "screw" and i.outdoor == outdoor]
    longest = max(s.screw_length_mm or 0 for s in screws)
    joints: list[Joint] = []
    too_thick = False
    for contact in checked.contacts:
        a, b = checked.infos[contact.a], checked.infos[contact.b]
        if {a.kind, b.kind} & {"piece", "bulk"} or frozenset((contact.a, contact.b)) in skip:
            continue
        n = _screw_count(contact)
        box_a, box_b = checked.boxes[contact.a], checked.boxes[contact.b]
        if contact.axis is None:
            ta, tb = box_a.dims[0], box_b.dims[0]
            t = min(ta, tb)
            cap = t + max(ta, tb) - 5
        else:
            ta, tb = box_a.size[contact.axis], box_b.size[contact.axis]
            t, cap = min(ta, tb), ta + tb - 5
        if t + 24.0 > longest:
            too_thick = True
        # Screw through the thinner part (on a tie the smaller one, e.g. a batten) into the other.
        va, vb = checked.boxes[contact.a].volume_mm3, checked.boxes[contact.b].volume_mm3
        swap = tb < ta or (tb == ta and vb < va)
        through, into = (contact.b, contact.a) if swap else (contact.a, contact.b)
        joints.append(Joint(through, into, _screw_for(t, cap, screws), n, contact.axis))
    return joints, too_thick


def _screw_count(contact: Contact) -> int:
    long_side = contact.extent[0]
    if long_side < SCREW_SPACING_MM - 50:
        return 2
    return max(2, math.ceil(long_side / SCREW_SPACING_MM) + 1)


def _missing_hardware(
    design: AssemblyDesign,
    params: dict[str, ParamValue],
    hardware: dict[str, int],
    catalog: Catalog,
) -> list[str]:
    """Steps that mention hinges, latches or handles need that hardware (listed or placed)."""
    present = {catalog.item(item_id).hardware_type for item_id, qty in hardware.items() if qty > 0}
    errors: list[str] = []
    for kind, (pattern, label) in _HARDWARE_MENTIONS.items():
        if kind in present:
            continue
        for step in design.steps:
            text = substitute(f"{step.title} {step.text}", params)
            if pattern.search(text):
                options = ", ".join(
                    i.id for i in catalog.items if i.designable and i.hardware_type == kind
                )
                errors.append(
                    f"Bauschritt '{step.title}' nennt {label}, aber unter hardware fehlt ein "
                    f"passender Beschlag mit Menge (z. B. {options})"
                )
                break
    return errors


def _surface_m2(checked: CheckedDesign) -> float:
    """Wood surface to treat (no fittings, masonry, roofing or concrete)."""
    total = 0.0
    for info, box in zip(checked.infos, checked.boxes, strict=True):
        if info.kind in {"piece", "bulk"}:
            continue
        total += box.surface_mm2
    return total / 1e6


def _weight_kg(checked: CheckedDesign, catalog: Catalog) -> float:
    total = 0.0
    for info, box in zip(checked.infos, checked.boxes, strict=True):
        if info.kind == "piece" or not info.item.material:
            continue
        material = catalog.materials.get(info.item.material)
        if material:
            total += box.volume_mm3 / 1e9 * material.density_kg_m3
    return total


def _tip_risk(checked: CheckedDesign, design: AssemblyDesign) -> tuple[bool, str | None]:
    """Whether a floor-standing object should be anchored, and a stability warning."""
    if design.support != "floor" or design.category == "building":
        return False, None
    lo, hi = bounds_of(checked.boxes)
    height = hi[2] - lo[2]
    feet = [b for b in checked.boxes if b.bounds()[0][2] <= TOUCH_TOL]
    flo, fhi = bounds_of(feet)
    depth = min(fhi[0] - flo[0], fhi[1] - flo[1])
    weight = sum(b.volume_mm3 for b in checked.boxes)
    cx = sum(b.center()[0] * b.volume_mm3 for b in checked.boxes) / weight
    cy = sum(b.center()[1] * b.volume_mm3 for b in checked.boxes) / weight
    warning = None
    if not (flo[0] <= cx <= fhi[0] and flo[1] <= cy <= fhi[1]):
        warning = "Der Schwerpunkt liegt außerhalb der Standfläche – das Objekt kann kippen."
    anchor = height >= TIP_MIN_HEIGHT and depth > 0 and height / depth > TIP_RATIO
    return anchor, warning


_DIRECTIONS = {
    0: ("von links", "von rechts"),
    1: ("von vorne", "von hinten"),
    2: ("von unten", "von oben"),
}
_SCREW_SIZE = re.compile(r"(\d+(?:[.,]\d+)?)\s*×\s*(\d+)\s*mm")


def _qty(value: Decimal) -> str:
    text = f"{value:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _dims(info: PartInfo) -> str:
    if info.kind == "bulk":
        unit = "m²" if info.item.bulk_basis == "area" else "m³"
        amount = f"{info.quantity:.2f}".replace(".", ",")
        return (
            f"{info.length_mm} × {info.width_mm} mm, {info.thickness_mm} mm stark, {amount} {unit}"
        )
    if info.kind == "linear":
        return f"{info.thickness_mm} × {info.width_mm} mm, {info.length_mm} mm lang"
    if info.kind == "sheet":
        return f"{info.length_mm} × {info.width_mm} mm, {info.thickness_mm} mm stark"
    return info.item.spec


def _screw_text(screw: CatalogItem) -> tuple[str, str]:
    """Screw size (e.g. '4 × 40 mm') and a matching pilot drill diameter."""
    match = _SCREW_SIZE.search(screw.spec)
    if not match:
        return screw.spec.split(",")[0], "2/3 des Schraubendurchmessers"
    diameter = float(match.group(1).replace(",", "."))
    pilot = f"{round(diameter * 0.6 * 2) / 2:g}".replace(".", ",")
    return f"{match.group(1)} × {match.group(2)} mm", f"Ø {pilot} mm"


def _direction(joint: Joint, checked: CheckedDesign) -> str:
    if joint.axis is None:
        return ""
    through = checked.boxes[joint.through].center()[joint.axis]
    into = checked.boxes[joint.into].center()[joint.axis]
    low, high = _DIRECTIONS[joint.axis]
    return f" {low if through < into else high}"


def _cut_details(
    checked: CheckedDesign, numbers: list[int], stock_plan: list[StockPlan], joints: JointPlan
) -> list[str]:
    """Bar by bar what to saw, and which sheet pieces to cut, with position numbers."""
    infos = checked.infos
    details: list[str] = []
    for plan in stock_plan:
        if not plan.bars:
            continue
        item_id = plan.item_id.split("@")[0]
        by_length: dict[int, list[int]] = defaultdict(list)
        for info, number in sorted(zip(infos, numbers, strict=True), key=lambda x: x[1]):
            if info.kind == "linear" and info.item.id == item_id:
                by_length[info.length_mm].append(number)
        for k, bar in enumerate(plan.bars, start=1):
            cuts = [(length, by_length[length].pop(0)) for length in bar]
            # Identical consecutive cuts read better as "6× 800 mm (Pos. 1)".
            runs: list[tuple[int, int, int]] = []
            for length, number in cuts:
                if runs and runs[-1][1:] == (length, number):
                    runs[-1] = (runs[-1][0] + 1, length, number)
                else:
                    runs.append((1, length, number))
            pieces = [
                f"{count}× {length} mm (Pos. {number})"
                if count > 1
                else f"{length} mm (Pos. {number})"
                for count, length, number in runs
            ]
            rest = plan.stock_length_mm - sum(bar) - 4 * max(0, len(bar) - 1)
            details.append(
                f"{plan.name}, Stange {k} von {plan.stock_count} ({_m(plan.stock_length_mm)}): "
                f"{' · '.join(pieces)} – Rest ca. {max(0, rest)} mm"
            )
    sheet_counts: dict[int, int] = defaultdict(int)
    sheet_infos: dict[int, PartInfo] = {}
    for info, number in zip(infos, numbers, strict=True):
        if info.kind == "sheet":
            sheet_counts[number] += 1
            sheet_infos[number] = info
    for number in sorted(sheet_counts):
        info = sheet_infos[number]
        details.append(
            f"Pos. {number} {info.part.name}: {sheet_counts[number]}× "
            f"{info.length_mm} × {info.width_mm} mm aus {info.item.name} {info.thickness_mm} mm"
        )
    noted: set[int] = set()
    for i, (info, number) in enumerate(zip(infos, numbers, strict=True)):
        if number in noted or info.kind in {"piece", "bulk"}:
            continue
        box = checked.boxes[i]
        note = _cut_note(box, joints.extra_mm.get(i, 0))
        if note is None:
            continue
        noted.add(number)
        if box.holes:
            note += (
                f" – Kontur von Zeichnung „Schablone Pos. {number}“ übertragen, für "
                "Ausschnitte innen ein 10-mm-Loch vorbohren, mit der Stichsäge sägen, Kanten "
                "schleifen"
            )
        elif box.shaped:
            note += (
                f" – Kontur von Zeichnung „Schablone Pos. {number}“ übertragen, mit der "
                "Stichsäge sägen, Kanten schleifen"
            )
        details.append(f"Pos. {number} {info.part.name}: {note}")
    return details


_BULK_WORK = {
    "concrete": "betonieren: Schalung stellen, Beton lagenweise einbringen und verdichten, "
    "Oberfläche abziehen und mehrere Tage feucht halten",
    "clay": "ausmauern: Lehmsteine im Verband mit Lehmmörtel, Dreikantleisten an den Hölzern, "
    "1 cm Fuge zum Holz",
    "aerated": "ausmauern: Porenbeton-Plansteine mit Dünnbettmörtel, Dreikantleisten an den "
    "Hölzern, Anschlussfuge zum Holz elastisch schließen",
    "tile": "eindecken: Unterdeckbahn, Konter- und Traglattung, Ziegel von der Traufe zum First",
    "wood_fiber": "fugenlos einpassen, Stöße versetzen",
    "larch": "montieren: Lattung, dann Bretter von unten nach oben mit Edelstahlschrauben",
}
_CARPENTRY = {
    "tenon": "einzapfen und mit Holznagel Ø 22 mm sichern (Bohrung 2–3 mm versetzt, zieht die Verbindung an)",
    "half_lap": "überblatten und mit Holznagel Ø 22 mm sichern",
    "notch": "mit der Kerve aufsetzen und je Stelle mit 1 Holzbauschraube 8 × 240 mm befestigen",
}


def _carpentry_details(
    works: list[JointWork], checked: CheckedDesign, numbers: list[int]
) -> list[str]:
    infos = checked.infos
    groups: dict[tuple[str, int, int], list[JointWork]] = defaultdict(list)
    for w in works:
        groups[(w.kind, numbers[w.part], numbers[w.into])].append(w)
    details: list[str] = []
    for (kind, a, b), items in groups.items():
        places = len(items)
        extra = sum(w.pegs for w in items)
        details.append(
            f"Pos. {a} {_name_of(a, infos, numbers)} in Pos. {b} {_name_of(b, infos, numbers)} "
            f"{_CARPENTRY[kind]}: {places} {'Stelle' if places == 1 else 'Stellen'}"
            + (f" ({extra} Holznägel)" if extra else "")
        )
    return details


def _assembly_details(
    indices: list[int],
    joints: list[tuple[Joint, bool]],
    checked: CheckedDesign,
    numbers: list[int],
    glue: bool,
) -> list[str]:
    """``joints`` carries whether both parts are new in this step (those are listed first)."""
    infos = checked.infos
    counts: dict[int, int] = defaultdict(int)
    sample: dict[int, PartInfo] = {}
    for i in indices:
        counts[numbers[i]] += 1
        sample[numbers[i]] = infos[i]
    details: list[str] = []
    if counts:
        parts = ", ".join(
            f"{counts[n]}× Pos. {n} {sample[n].part.name} ({_dims(sample[n])})"
            for n in sorted(counts)
        )
        details.append(f"Bereitlegen: {parts}")

    groups: dict[tuple[int, int, str, int, str], int] = {}
    screw_of: dict[str, CatalogItem] = {}
    for joint, _ in sorted(joints, key=lambda j: not j[1]):
        key = (
            numbers[joint.through],
            numbers[joint.into],
            joint.screw.id,
            joint.count,
            _direction(joint, checked),
        )
        groups[key] = groups.get(key, 0) + 1
        screw_of[joint.screw.id] = joint.screw
    for (a, b, screw_id, count, direction), places in groups.items():
        size, pilot = _screw_text(screw_of[screw_id])
        name_a, name_b = _name_of(a, infos, numbers), _name_of(b, infos, numbers)
        where = "Stelle" if places == 1 else "Stellen"
        details.append(
            f"Pos. {a} {name_a}{direction} in Pos. {b} {name_b} schrauben: {places} {where} "
            f"mit je {count} Schrauben {size} ({places * count} Stk); {pilot} vorbohren, ansenken"
            + ("; Kontaktflächen vorher dünn mit Holzleim bestreichen" if glue else "")
        )

    bulk: dict[int, PartInfo] = {}
    for i in indices:
        if infos[i].kind == "bulk":
            bulk.setdefault(numbers[i], infos[i])
    for n, info in sorted(bulk.items()):
        work = _BULK_WORK.get(info.item.material or "", "einbauen")
        details.append(f"Pos. {n} {info.part.name} ({info.item.name}) {work}")

    pieces = {i for i in indices if infos[i].kind == "piece"}
    piece_counts: dict[int, int] = defaultdict(int)
    partners: dict[int, set[int]] = defaultdict(set)
    for i in pieces:
        piece_counts[numbers[i]] += 1
    for contact in checked.contacts:
        for p, other in ((contact.a, contact.b), (contact.b, contact.a)):
            if p in pieces and infos[other].kind != "piece":
                partners[numbers[p]].add(numbers[other])
    for n in sorted(piece_counts):
        on = ", ".join(f"Pos. {o} {_name_of(o, infos, numbers)}" for o in sorted(partners[n]))
        details.append(
            f"{piece_counts[n]}× Pos. {n} {sample[n].part.name}"
            + (f" auf {on}" if on else "")
            + " anschrauben, Lage siehe Zeichnung (Schrauben passend zum Beschlag, meist beiliegend)"
        )
    return details


def _name_of(number: int, infos: list[PartInfo], numbers: list[int]) -> str:
    return infos[numbers.index(number)].part.name


def _instructions(
    design: AssemblyDesign,
    params: dict[str, ParamValue],
    checked: CheckedDesign,
    numbers: list[int],
    joints: list[Joint],
    bom_lines: list[BomLine],
    stock_plan: list[StockPlan],
    hardware: dict[str, int],
    catalog: Catalog,
    anchor: bool,
    plan: JointPlan,
) -> list[InstructionStep]:
    """Step-by-step instructions: buy, cut bar by bar, assemble with concrete connections."""
    origin = Origin.AI if design.origin == Origin.AI else Origin.ENGINE
    infos = checked.infos
    steps: list[InstructionStep] = []

    def add(title: str, text: str, details: list[str], step_origin: Origin = Origin.ENGINE) -> None:
        steps.append(
            InstructionStep(
                number=len(steps) + 1,
                title=title,
                text=text,
                origin=step_origin,
                details=details,
            )
        )

    add(
        "Material einkaufen",
        "Kaufe alles laut Einkaufsliste und wähle gerade, möglichst astarme Hölzer."
        + (
            " Maßholz in Sonderquerschnitten rechtzeitig im Holzfachhandel bestellen."
            if any(info.item.made_to_order for info in infos)
            else ""
        ),
        [f"{_qty(line.quantity)}× {line.name} ({line.spec})" for line in bom_lines],
    )
    has_sheets = any(info.kind == "sheet" for info in infos)
    add(
        "Teile zuschneiden und beschriften",
        "Säge die Teile Stange für Stange in der angegebenen Reihenfolge zu, längste Teile zuerst. "
        "Miss jedes Maß neu vom frisch gesägten Ende und zeichne mit dem Winkel an; der "
        "Sägeschnitt kostet ca. 4 mm. Schreibe die Positionsnummer sofort mit Bleistift auf jedes "
        "Teil, brich alle Kanten mit Schleifpapier (Körnung 120) und schleife die Flächen vor."
        + (" Platten kannst du im Baumarkt nach Maß zuschneiden lassen." if has_sheets else ""),
        _cut_details(checked, numbers, stock_plan, plan),
    )
    if plan.works:
        groups: dict[tuple[str, int, int, str], int] = defaultdict(int)
        for w in plan.works:
            groups[(w.kind, numbers[w.part], numbers[w.into], w.text)] += 1
        add(
            "Holzverbindungen anreißen und ausarbeiten",
            "Reiße alle Verbindungen vom Bezugsmaß aus an (Schnurschlag, Zimmermannswinkel) und "
            "nummeriere jede Stelle mit Abbundzeichen. Zapfen und Blätter mit der Säge "
            "einschneiden und mit dem Stemmeisen ausarbeiten; Zapfenlöcher bohren oder stemmen. "
            "Jede Verbindung trocken zur Probe stecken.",
            [
                f"Pos. {a} {_name_of(a, infos, numbers)} → Pos. {b} "
                f"{_name_of(b, infos, numbers)}: {text} ({count}×)"
                for (_, a, b, text), count in groups.items()
            ],
        )

    # Each part is mounted in the first design step that names it; the rest at the end.
    step_of = [len(design.steps)] * len(infos)
    for i, info in enumerate(infos):
        for k, step in enumerate(design.steps):
            if info.part.spec_id in step.parts:
                step_of[i] = k
                break
    placed_kinds: dict[str, set[str]] = defaultdict(set)
    mentioned: set[str] = set()
    stages: list[tuple[str, str, Origin, list[int]]] = [
        (substitute(step.title, params), substitute(step.text, params), origin, [])
        for step in design.steps
    ]
    rest = [i for i, k in enumerate(step_of) if k == len(design.steps)]
    if rest:
        if design.steps:
            stages.append(
                (
                    "Restliche Teile anbauen",
                    "Bringe die übrigen Teile gemäß Isometrie und Ansichten an.",
                    Origin.ENGINE,
                    [],
                )
            )
        else:
            stages.append(
                (
                    "Zusammenbauen",
                    "Setze die Teile gemäß Isometrie und Ansichten in der Reihenfolge der "
                    "Positionsnummern zusammen. Richte jedes Teil vor dem Verschrauben mit dem "
                    "Winkel aus und fixiere es mit Zwingen.",
                    Origin.ENGINE,
                    [],
                )
            )
    for i, k in enumerate(step_of):
        stages[k][3].append(i)
    for item_id in hardware:
        hardware_type = catalog.item(item_id).hardware_type
        if hardware_type:
            placed_kinds[hardware_type].add(item_id)

    for k, (title, text, step_origin, indices) in enumerate(stages):
        # A joint is made when its later part gets mounted.
        step_joints = [
            (j, step_of[j.through] == step_of[j.into])
            for j in joints
            if max(step_of[j.through], step_of[j.into]) == k
        ]
        details = _assembly_details(
            indices,
            step_joints,
            checked,
            numbers,
            any(line.item_id == "glue_d3_750" for line in bom_lines),
        )
        details += _carpentry_details(
            [w for w in plan.works if max(step_of[w.part], step_of[w.into]) == k],
            checked,
            numbers,
        )
        for kind, (pattern, _) in _HARDWARE_MENTIONS.items():
            if pattern.search(f"{title} {text}"):
                for item_id in sorted(placed_kinds.get(kind, set()) - mentioned):
                    item = catalog.item(item_id)
                    details.append(f"Beschlag: {hardware[item_id]}× {item.name} ({item.spec})")
                    mentioned.add(item_id)
        if k == len(stages) - 1:
            for item_id, quantity in hardware.items():
                if item_id in mentioned or item_id == "wall_anchor_set":
                    continue
                item = catalog.item(item_id)
                details.append(f"Außerdem anbringen: {quantity}× {item.name} ({item.spec})")
        add(title, text, details, step_origin)

    if design.finish:
        finish = catalog.find(design.finish)
        finish_name = finish.name if finish else "Holzschutz"
        add(
            "Oberfläche behandeln",
            f"Alle Holzflächen staubfrei schleifen und {FINISH_COATS}× dünn mit {finish_name} "
            + (
                "streichen; Hirnholz und Unterkanten besonders satt."
                if design.use == "outdoor"
                else "streichen."
            ),
            [
                "Staub mit Handfeger und feuchtem Tuch entfernen",
                "1. Anstrich dünn auftragen und nach Herstellerangabe trocknen lassen",
                "Zwischenschliff mit Körnung 180–240, Schleifstaub entfernen",
                f"{FINISH_COATS}. Anstrich auftragen und vollständig trocknen lassen",
            ],
        )
    if anchor:
        add(
            "Gegen Kippen sichern",
            "Das Objekt ist hoch und schmal: mit der Kippsicherung an der Wand befestigen "
            "(Dübel passend zum Mauerwerk wählen, keine Leitungen anbohren).",
            [
                "Aufstellen und mit der Wasserwaage lotrecht ausrichten",
                "Winkel oben an der Rückseite anschrauben, Bohrlöcher an der Wand anzeichnen",
                "Leitungen mit einem Ortungsgerät prüfen, bohren, dübeln und festschrauben",
            ],
        )
    return steps


def build_design(
    design: AssemblyDesign, params: dict[str, ParamValue], catalog: Catalog
) -> PackBuild:
    """Build everything for a design with validated, effective parameters."""
    parts = resolve_parts(design, params)
    checked = check_design(design, parts, catalog)
    plan = plan_joints(design, checked)
    infos = _with_tenons(checked, plan)
    checked.infos = infos
    building = design.category == "building"
    outdoor = design.use == "outdoor"
    positions, numbers = _positions(infos)
    bom = BomBuilder(catalog)
    stock_plan: list[StockPlan] = []
    warnings: list[str] = []

    linear: dict[str, list[int]] = defaultdict(list)
    sheets: dict[str, list[tuple[int, int]]] = defaultdict(list)
    bulk: dict[str, float] = defaultdict(float)
    placed_pieces: dict[str, int] = defaultdict(int)
    for info in infos:
        if info.kind == "linear":
            linear[info.item.id].append(info.length_mm)
        elif info.kind == "sheet":
            sheets[info.item.id].append((info.length_mm, info.width_mm))
        elif info.kind == "bulk":
            bulk[info.item.id] += info.quantity
        else:
            placed_pieces[info.item.id] += 1
    for item_id, lengths in linear.items():
        stock_plan.append(_linear_stock(catalog.item(item_id), lengths, bom))
    for item_id, pieces in sheets.items():
        stock_plan.append(_sheet_stock(catalog.item(item_id), pieces, bom))
    for item_id, amount in bulk.items():
        unit = catalog.item(item_id).unit
        need = Decimal(str(amount)) * BULK_RESERVE
        bought = (need * 10).to_integral_value(rounding="ROUND_CEILING") / 10
        bom.add(
            item_id,
            max(bought, Decimal("0.1")),
            note=f"netto {amount:.2f} {unit}, +5 % Verschnitt".replace(".", ","),
            used=Decimal(str(amount)),
        )
    for item_id, count in placed_pieces.items():
        bom.add(item_id, count)
    if plan.pegs:
        bom.add("peg_oak_22", plan.pegs, note="für Zapfen und Blätter")
    if plan.screws:
        timber_screw = catalog.item("screw_timber_8x240_50")
        assert timber_screw.pack_size is not None
        bom.add(
            timber_screw.id,
            math.ceil(Decimal(plan.screws) * SCREW_RESERVE / timber_screw.pack_size),
            note=f"ca. {plan.screws} Stk für Kerven",
            used=Decimal(plan.screws) / timber_screw.pack_size,
        )

    hardware: dict[str, int] = defaultdict(int)
    errors: list[str] = []
    notes: dict[str, str] = {}
    for spec in design.hardware:
        if not is_included(spec.when, params):
            continue
        item = catalog.find(spec.item)
        if item is None or not item.designable or item.kind != "piece":
            errors.append(f"Beschlag '{spec.item}' gibt es nicht im Katalog (siehe list_materials)")
            continue
        quantity = math.ceil(resolve_quantity(spec.quantity, params) - 1e-9)
        if quantity > 500:
            errors.append(f"Beschlag '{spec.item}': Menge {quantity} ist unplausibel")
            continue
        hardware[item.id] += quantity
        if spec.note:
            notes[item.id] = spec.note
    errors.extend(_missing_hardware(design, params, {**placed_pieces, **hardware}, catalog))
    if errors:
        raise DesignError(errors)

    anchor, tip_warning = _tip_risk(checked, design)
    if anchor:
        hardware["wall_anchor_set"] = max(hardware.get("wall_anchor_set", 0), 1)
    if tip_warning:
        warnings.append(tip_warning)
    for item_id, quantity in hardware.items():
        bom.add(item_id, quantity, note=notes.get(item_id))

    screw_total = 0
    joints = 0
    screw_joints: list[Joint] = []
    if design.auto_screws:
        screw_joints, too_thick = _screws(checked, outdoor, catalog, plan.pairs)
        joints = len(screw_joints)
        screw_counts: dict[str, int] = defaultdict(int)
        for joint in screw_joints:
            screw_counts[joint.screw.id] += joint.count
        for item_id, count in sorted(screw_counts.items()):
            item = catalog.item(item_id)
            assert item.pack_size is not None
            packs = math.ceil(Decimal(count) * SCREW_RESERVE / item.pack_size)
            bom.add(
                item_id,
                packs,
                note=f"ca. {count} Stk benötigt",
                used=Decimal(count) / item.pack_size,
            )
            screw_total += count
        if too_thick:
            warnings.append(
                "Bei dicken Querschnitten reichen Schrauben nicht immer: Schlossschrauben, "
                "Gewindestangen oder Winkelverbinder prüfen."
            )
    if not outdoor and joints:
        bom.add(
            "glue_d3_750",
            math.ceil(joints / JOINTS_PER_GLUE),
            note="für Leimverbindungen",
            used=Decimal(joints) / JOINTS_PER_GLUE,
        )

    surface = _surface_m2(checked)
    if design.finish:
        item = catalog.find(design.finish)
        if item is None or item.kind != "finish" or item.coverage_m2 is None:
            raise DesignError([f"Oberflächenmittel '{design.finish}' gibt es nicht im Katalog"])
        cans = math.ceil(Decimal(str(surface)) * FINISH_COATS / item.coverage_m2)
        bom.add(
            item.id,
            cans,
            note=f"{surface:.1f} m² × {FINISH_COATS} Anstriche".replace(".", ","),
            used=Decimal(str(surface)) * FINISH_COATS / item.coverage_m2,
        )
        if outdoor and not item.outdoor:
            warnings.append(f"{item.name} ist nicht für außen geeignet.")

    if outdoor:
        unsuitable = sorted(
            {
                i.item.name
                for i in infos
                if i.kind != "piece" and not i.item.outdoor and not _sheltered(i, building)
            }
        )
        unsuitable += sorted(
            {
                catalog.item(item_id).name
                for item_id in hardware
                if not catalog.item(item_id).outdoor
            }
        )
        if unsuitable:
            warnings.append(
                "Für draußen ungeeignet bzw. nur mit Schutz haltbar: " + ", ".join(unsuitable) + "."
            )

    lo, hi = bounds_of(checked.boxes)
    w, d, h = (round(hi[k] - lo[k]) for k in range(3))
    weight = _weight_kg(checked, catalog)
    linear_bars = sum(s.stock_count for s in stock_plan if s.bars)
    sheet_count = sum(s.stock_count for s in stock_plan if not s.bars)
    stock_text = ", ".join(
        t
        for t in (
            f"{linear_bars} Stangen/Bretter" if linear_bars else "",
            f"{sheet_count} Platte{'n' if sheet_count != 1 else ''}" if sheet_count else "",
        )
        if t
    )
    key_figures = {
        "Außenmaße (B × T × H)": f"{w} × {d} × {h} mm",
        "Bauteile": f"{len(infos)} Teile in {len(positions)} Positionen",
        "Gewicht ca.": f"{weight:.0f} kg",
        "Einkauf Holz": stock_text or "–",
        "Schrauben": f"ca. {screw_total} Stk" if screw_total else "–",
        "Holzoberfläche": f"{surface:.1f} m²".replace(".", ","),
    }
    if plan.works:
        key_figures["Holzverbindungen"] = f"{len(plan.works)}" + (
            f", {plan.pegs} Holznägel" if plan.pegs else ""
        )
    if building:
        lo_z = min(b.bounds()[0][2] for b in checked.boxes)
        key_figures["Gebäudehöhe über Gelände"] = f"{round(hi[2])} mm"
        if lo_z < 0:
            key_figures["Gründungstiefe"] = f"{round(-lo_z)} mm"
    summary = substitute(design.summary, params).strip() or design.object_type
    summary = f"{summary} – {w} × {d} × {h} mm"

    tool_ids = ["tool_measure", "tool_saw", "tool_drill_driver", "tool_drill_bit"]
    tool_ids += ["tool_countersink", "tool_clamps", "tool_sander"]
    if sheets or any(b.shaped or b.holes for b in checked.boxes):
        tool_ids.append("tool_jigsaw")
    if plan.works:
        tool_ids += ["tool_chisel", "tool_chainsaw_mortiser"]
    if any(i.item.category == "masonry" for i in infos):
        tool_ids.append("tool_mixer")
    if design.finish:
        tool_ids.append("tool_brush")
    if anchor or design.support == "wall":
        tool_ids.append("tool_level")
    tool_ids.append("tool_ppe")
    tools = [Tool(name=catalog.tool(t).name) for t in tool_ids]
    tools_cost = sum_money(
        [money(catalog.tool(t).price_min, catalog.tool(t).price_max) for t in tool_ids]
    )

    notices: list[Notice] = []
    if design.origin == Origin.AI:
        notices.append(
            Notice(
                code="AI_DRAFT",
                severity=Severity.WARNING,
                message=(
                    "KI-Entwurf: Die Konstruktion hat eine KI vorgeschlagen; sie ist nicht "
                    "fachlich geprüft. Mengen, Kosten und Zeichnungen berechnet die Engine aus dem "
                    "Entwurf – prüfe Stabilität und Verbindungen vor dem Bau."
                ),
            )
        )
    else:
        notices.append(
            Notice(
                code="TEMPLATE",
                severity=Severity.INFO,
                message="Vorlage: Konstruktion aus der Homeworking-Vorlagensammlung, an deine Maße angepasst.",
            )
        )
    for index, message in enumerate(warnings):
        notices.append(
            Notice(code=f"CHECK_{index + 1}", severity=Severity.WARNING, message=message)
        )
    if anchor:
        notices.append(
            Notice(
                code="TIP",
                severity=Severity.WARNING,
                message="Hoch und schmal: Kippsicherung an der Wand ist eingeplant und erforderlich.",
                rule_id="FD-TIP",
            )
        )
    if building:
        notices.append(
            Notice(
                code="BUILDING",
                severity=Severity.WARNING,
                message=(
                    "Gebäude: Tragwerk, Gründung, Dach und Aussteifung brauchen eine Statik von "
                    "einem Tragwerksplaner, in der Regel auch eine Baugenehmigung nach "
                    "Landesbauordnung (Bauamt fragen). Die Engine prüft nur Geometrie, Mengen und "
                    "Kosten – keine Standsicherheit, keinen Wärme-, Feuchte-, Brand- oder "
                    "Schallschutz. Querschnitte vor dem Bau vom Fachplaner bestätigen lassen."
                ),
                rule_id="FD-BUILD",
            )
        )
    else:
        notices.append(
            Notice(
                code="NO_STATICS",
                severity=Severity.INFO,
                message=(
                    "Planungshilfe ohne Statik: nicht für tragende Bauteile, Absturzsicherungen "
                    "oder Spielgeräte nach Norm verwenden."
                ),
            )
        )

    components = [
        Component(
            guid=_guid(info.part.key),
            ifc_type={"linear": "IfcMember", "sheet": "IfcPlate"}.get(
                info.kind, "IfcDiscreteAccessory"
            ),
            role=info.part.spec_id,
            name=info.part.name,
            material_id=info.item.id,
            profile=(
                Profile(thickness_mm=info.thickness_mm, width_mm=info.width_mm)
                if info.kind != "piece"
                else None
            ),
            length_mm=info.length_mm or None,
        )
        for info in infos
    ]
    solids = [
        _solid(info, box, number, catalog)
        for info, box, number in zip(infos, checked.boxes, numbers, strict=True)
    ]
    legend = {_tone(info, catalog): _material_label(info, catalog) for info in infos}
    drawings = build_drawings(
        design.object_type,
        checked.boxes,
        numbers,
        [p.name for p in positions],
        solids,
        legend,
        wall_side=design.support == "wall",
    )
    templated: set[int] = set()
    for info, box, number in zip(infos, checked.boxes, numbers, strict=True):
        if (
            (box.shaped or box.holes)
            and info.kind in {"linear", "sheet"}
            and number not in templated
            and len(templated) < MAX_TEMPLATES
        ):
            templated.add(number)
            drawings.append(
                build_template(box, number, info.part.name, _tone(info, catalog), legend)
            )

    return PackBuild(
        summary=summary,
        key_figures=key_figures,
        components=components,
        bom=bom.lines,
        cut_list=_cut_list(positions, numbers, checked, plan),
        stock_plan=stock_plan,
        fill_layers=[],
        tools=tools,
        costs=CostSummary(
            material=bom.total(),
            tools_optional=tools_cost,
            note=(
                "Richtpreise (Stand Katalog), ohne Lieferung. Werkzeugkosten nur, falls nichts "
                "vorhanden ist (Leihen/Mieten oft günstiger)."
            ),
        ),
        drawings=drawings,
        instructions=_instructions(
            design,
            params,
            checked,
            numbers,
            screw_joints,
            bom.lines,
            stock_plan,
            {item_id: q for item_id, q in hardware.items() if q > 0},
            catalog,
            anchor,
            plan,
        ),
        notices=notices,
        rules=list(RULES.values()),
        solids=solids,
    )


def _with_tenons(checked: CheckedDesign, plan: JointPlan) -> list[PartInfo]:
    """Add tenon lengths to the stock length of members (they are cut longer)."""
    infos: list[PartInfo] = []
    errors: list[str] = []
    for i, info in enumerate(checked.infos):
        extra = plan.extra_mm.get(i, 0)
        if extra and info.kind == "linear":
            length = info.length_mm + extra
            longest = max(info.item.stock_lengths_mm)
            if length > longest:
                errors.append(
                    f"Bauteil '{info.part.key}': mit Zapfen {length} mm, längste Handelslänge "
                    f"{longest} mm – teilen oder anderes Holz wählen"
                )
            info = replace(info, length_mm=length)
        infos.append(info)
    if errors:
        raise DesignError(errors)
    return infos


def _sheltered(info: PartInfo, building: bool) -> bool:
    """Indoor-grade parts inside a building's envelope (insulation, frame behind cladding)."""
    return building and info.item.category in {"insulation", "wood"}


def _solid(info: PartInfo, box: Box, number: int, catalog: Catalog) -> Solid:
    rotation = info.part.rotation
    if box.aligned or (rotation is not None and box.part.shape is None and not box.holes):
        return Solid(
            position=number,
            part_id=info.part.key,
            name=info.part.name,
            material=info.item.name,
            tone=_tone(info, catalog),
            size=info.part.size,
            at=info.part.at,
            rotation=SolidRotation(axis=rotation[0], deg=rotation[1]) if rotation else None,
        )
    lo, hi = box.bounds()
    vertices, triangles = box.mesh()
    return Solid(
        position=number,
        part_id=info.part.key,
        name=info.part.name,
        material=info.item.name,
        tone=_tone(info, catalog),
        size=(round(hi[0] - lo[0], 1), round(hi[1] - lo[1], 1), round(hi[2] - lo[2], 1)),
        at=(round(lo[0], 1), round(lo[1], 1), round(lo[2], 1)),
        mesh=SolidMesh(vertices=vertices, triangles=triangles),
    )


def _tone(info: PartInfo, catalog: Catalog) -> str:
    material = catalog.materials.get(info.item.material or "")
    return material.tone if material else "steel"


def _material_label(info: PartInfo, catalog: Catalog) -> str:
    material = catalog.materials.get(info.item.material or "")
    return material.label if material else info.item.name


__all__ = ["DESIGN_PACK_ID", "DESIGN_PACK_VERSION", "build_design", "check_design"]
