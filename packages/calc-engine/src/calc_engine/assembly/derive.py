"""Derive BOM, cut list, costs, instructions and notices from a checked design (ADR-0004)."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from calc_engine.assembly.check import CheckedDesign, PartInfo, check_design
from calc_engine.assembly.geometry import TOUCH_TOL, Contact, bounds_of
from calc_engine.assembly.projection import build_drawings
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
    SolidRotation,
    StockPlan,
    Tool,
)

DESIGN_PACK_ID = "design"
DESIGN_PACK_VERSION = "1.0.0"
_GUID_NS = uuid5(NAMESPACE_URL, "https://homeworking.example/packs/design")
SCREW_SPACING_MM = 250
SCREW_RESERVE = Decimal("1.1")
FINISH_COATS = 2
JOINTS_PER_GLUE = 60
TIP_RATIO = 2.5
TIP_MIN_HEIGHT = 900
LUMBER_NOTE = "Maßholz: im Holzfachhandel/Hobelwerk in diesem Querschnitt bestellen"
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
            id="FD-SIZE", version="1", title="Freie Entwürfe max. 4 × 4 m Grundfläche, 2,5 m Höhe"
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
        key = (info.part.name, info.item.id, info.length_mm, info.width_mm)
        if key not in keys:
            keys[key] = len(positions) + 1
            positions.append(Position(keys[key], info.part.spec_id, info.part.name, info))
        numbers.append(keys[key])
    return positions, numbers


def _cut_list(positions: list[Position], numbers: list[int]) -> list[CutLine]:
    counts: dict[int, int] = defaultdict(int)
    for n in numbers:
        counts[n] += 1
    lines: list[CutLine] = []
    for pos in positions:
        info = pos.info
        if info.kind == "piece":
            continue
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


def _screws(
    checked: CheckedDesign, outdoor: bool, catalog: Catalog
) -> tuple[dict[str, int], int, bool]:
    screws = [i for i in catalog.items if i.kind == "screw" and i.outdoor == outdoor]
    longest = max(s.screw_length_mm or 0 for s in screws)
    counts: dict[str, int] = defaultdict(int)
    joints = 0
    too_thick = False
    for contact in checked.contacts:
        a, b = checked.infos[contact.a], checked.infos[contact.b]
        if a.kind == "piece" or b.kind == "piece":
            continue
        joints += 1
        n = _screw_count(contact)
        if contact.axis is None:
            t = min(min(a.part.size), min(b.part.size))
            cap = t + max(min(a.part.size), min(b.part.size)) - 5
        else:
            ta, tb = a.part.size[contact.axis], b.part.size[contact.axis]
            t, cap = min(ta, tb), ta + tb - 5
        if t + 24.0 > longest:
            too_thick = True
        counts[_screw_for(t, cap, screws).id] += n
    return counts, joints, too_thick


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


def _surface_m2(infos: list[PartInfo]) -> float:
    total = 0.0
    for info in infos:
        if info.kind == "piece":
            continue
        x, y, z = info.part.size
        total += 2 * (x * y + y * z + x * z)
    return total / 1e6


def _weight_kg(infos: list[PartInfo], catalog: Catalog) -> float:
    total = 0.0
    for info in infos:
        if info.kind == "piece" or not info.item.material:
            continue
        material = catalog.materials.get(info.item.material)
        if material:
            x, y, z = info.part.size
            total += x * y * z / 1e9 * material.density_kg_m3
    return total


def _tip_risk(checked: CheckedDesign, design: AssemblyDesign) -> tuple[bool, str | None]:
    """Whether a floor-standing object should be anchored, and a stability warning."""
    if design.support != "floor":
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


def _instructions(
    design: AssemblyDesign,
    params: dict[str, ParamValue],
    infos: list[PartInfo],
    numbers: list[int],
    has_sheets: bool,
    anchor: bool,
) -> list[InstructionStep]:
    origin = Origin.AI if design.origin == Origin.AI else Origin.ENGINE
    by_spec: dict[str, set[int]] = defaultdict(set)
    for info, number in zip(infos, numbers, strict=True):
        by_spec[info.part.spec_id].add(number)
    steps: list[InstructionStep] = []

    def add(title: str, text: str, step_origin: Origin = Origin.ENGINE) -> None:
        steps.append(
            InstructionStep(number=len(steps) + 1, title=title, text=text, origin=step_origin)
        )

    add(
        "Material besorgen und zuschneiden",
        "Kaufe das Material laut Materialliste und schneide alle Teile nach der Zuschnittliste "
        "zu; beschrifte sie mit ihrer Positionsnummer."
        + (" Platten kannst du im Baumarkt nach Maß zuschneiden lassen." if has_sheets else "")
        + " Kanten leicht brechen und die Teile vor dem Zusammenbau schleifen.",
    )
    for step in design.steps:
        numbers = sorted({n for part_id in step.parts for n in by_spec.get(part_id, [])})
        suffix = f" (Pos. {', '.join(str(n) for n in numbers)})" if numbers else ""
        add(substitute(step.title, params), substitute(step.text, params) + suffix, origin)
    if not design.steps:
        add(
            "Zusammenbauen",
            "Setze die Teile gemäß Isometrie und Ansichten zusammen. Verschraube jede "
            "Kontaktfläche mit mindestens zwei Schrauben; Schraubenlöcher vorbohren und ansenken.",
        )
    if design.finish:
        add(
            "Oberfläche behandeln",
            f"Alle Holzflächen staubfrei schleifen und {FINISH_COATS}× dünn streichen; "
            "Zwischenschliff nach dem ersten Anstrich.",
        )
    if anchor:
        add(
            "Gegen Kippen sichern",
            "Das Objekt ist hoch und schmal: mit der Kippsicherung an der Wand befestigen "
            "(Dübel passend zum Mauerwerk wählen, keine Leitungen anbohren).",
        )
    return steps


def build_design(
    design: AssemblyDesign, params: dict[str, ParamValue], catalog: Catalog
) -> PackBuild:
    """Build everything for a design with validated, effective parameters."""
    parts = resolve_parts(design, params)
    checked = check_design(design, parts, catalog)
    infos = checked.infos
    outdoor = design.use == "outdoor"
    positions, numbers = _positions(infos)
    bom = BomBuilder(catalog)
    stock_plan: list[StockPlan] = []
    warnings: list[str] = []

    linear: dict[str, list[int]] = defaultdict(list)
    sheets: dict[str, list[tuple[int, int]]] = defaultdict(list)
    placed_pieces: dict[str, int] = defaultdict(int)
    for info in infos:
        if info.kind == "linear":
            linear[info.item.id].append(info.length_mm)
        elif info.kind == "sheet":
            sheets[info.item.id].append((info.length_mm, info.width_mm))
        else:
            placed_pieces[info.item.id] += 1
    for item_id, lengths in linear.items():
        stock_plan.append(_linear_stock(catalog.item(item_id), lengths, bom))
    for item_id, pieces in sheets.items():
        stock_plan.append(_sheet_stock(catalog.item(item_id), pieces, bom))
    for item_id, count in placed_pieces.items():
        bom.add(item_id, count)

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
    if design.auto_screws:
        screw_counts, joints, too_thick = _screws(checked, outdoor, catalog)
        for item_id, count in sorted(screw_counts.items()):
            item = catalog.item(item_id)
            assert item.pack_size is not None
            packs = math.ceil(Decimal(count) * SCREW_RESERVE / item.pack_size)
            bom.add(item_id, packs, note=f"ca. {count} Stk benötigt")
            screw_total += count
        if too_thick:
            warnings.append(
                "Bei dicken Querschnitten reichen Schrauben nicht immer: Schlossschrauben, "
                "Gewindestangen oder Winkelverbinder prüfen."
            )
    if not outdoor and joints:
        bom.add("glue_d3_750", math.ceil(joints / JOINTS_PER_GLUE), note="für Leimverbindungen")

    surface = _surface_m2(infos)
    if design.finish:
        item = catalog.find(design.finish)
        if item is None or item.kind != "finish" or item.coverage_m2 is None:
            raise DesignError([f"Oberflächenmittel '{design.finish}' gibt es nicht im Katalog"])
        cans = math.ceil(Decimal(str(surface)) * FINISH_COATS / item.coverage_m2)
        bom.add(
            item.id, cans, note=f"{surface:.1f} m² × {FINISH_COATS} Anstriche".replace(".", ",")
        )
        if outdoor and not item.outdoor:
            warnings.append(f"{item.name} ist nicht für außen geeignet.")

    if outdoor:
        unsuitable = sorted(
            {i.item.name for i in infos if i.kind != "piece" and not i.item.outdoor}
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
    weight = _weight_kg(infos, catalog)
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
    summary = substitute(design.summary, params).strip() or design.object_type
    summary = f"{summary} – {w} × {d} × {h} mm"

    tool_ids = ["tool_measure", "tool_saw", "tool_drill_driver", "tool_drill_bit"]
    tool_ids += ["tool_countersink", "tool_clamps", "tool_sander"]
    if sheets:
        tool_ids.append("tool_jigsaw")
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
    notices.append(
        Notice(
            code="NO_STATICS",
            severity=Severity.INFO,
            message=(
                "Planungshilfe ohne Statik: nicht für tragende Bauteile, Absturzsicherungen oder "
                "Spielgeräte nach Norm verwenden."
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
        Solid(
            position=number,
            part_id=info.part.key,
            name=info.part.name,
            material=info.item.name,
            tone=_tone(info, catalog),
            size=info.part.size,
            at=info.part.at,
            rotation=(
                SolidRotation(axis=info.part.rotation[0], deg=info.part.rotation[1])
                if info.part.rotation
                else None
            ),
        )
        for info, number in zip(infos, numbers, strict=True)
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

    return PackBuild(
        summary=summary,
        key_figures=key_figures,
        components=components,
        bom=bom.lines,
        cut_list=_cut_list(positions, numbers),
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
        instructions=_instructions(design, params, infos, numbers, bool(sheets), anchor),
        notices=notices,
        rules=list(RULES.values()),
        solids=solids,
    )


def _tone(info: PartInfo, catalog: Catalog) -> str:
    material = catalog.materials.get(info.item.material or "")
    return material.tone if material else "steel"


def _material_label(info: PartInfo, catalog: Catalog) -> str:
    material = catalog.materials.get(info.item.material or "")
    return material.label if material else info.item.name


__all__ = ["DESIGN_PACK_ID", "DESIGN_PACK_VERSION", "build_design", "check_design"]
