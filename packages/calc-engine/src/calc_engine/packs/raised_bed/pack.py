"""Raised bed construction pack (Hochbeet)."""

from __future__ import annotations

import math
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel

from calc_engine.catalog import BomBuilder, Catalog, money, sum_money
from calc_engine.cutting import plan_cuts
from calc_engine.pack import PackBuild, VariantSpec
from calc_engine.packs.raised_bed.drawings import build_drawings
from calc_engine.packs.raised_bed.geometry import (
    BOARD_STOCK,
    BOARD_T,
    BOARD_W,
    LINER_ROLL_LENGTH,
    MAX_FREE_SPAN,
    MESH_ROLL_LENGTH,
    POST,
    POST_STOCK,
    SOIL_BAG_L,
    RaisedBedGeometry,
    compute_geometry,
)
from calc_engine.packs.raised_bed.params import WOOD_LABELS, RaisedBedParams, Wood
from construction_model.model import (
    Component,
    CostSummary,
    CutLine,
    FillLayer,
    InstructionStep,
    Notice,
    Profile,
    RuleRef,
    Severity,
    StockPlan,
    Tool,
)

PACK_ID = "raised_bed"
PACK_VERSION = "1.0.0"
HIGH_BED_FROM = 900
_GUID_NS = uuid5(NAMESPACE_URL, "https://homeworking.example/packs/raised_bed")

RULES: dict[str, RuleRef] = {
    r.id: r
    for r in [
        RuleRef(id="RB-ROWS", version="1", title="Wandhöhe = Brettreihen × 145 mm (aufgerundet)"),
        RuleRef(
            id="RB-SPAN",
            version="1",
            title=f"Freie Wandlänge max. {MAX_FREE_SPAN} mm zwischen Pfosten (Erddruck)",
        ),
        RuleRef(
            id="RB-TIE",
            version="1",
            title="Je Zwischenpfostenpaar Zuganker M10; ab Wandhöhe > 600 mm zwei Ebenen",
        ),
        RuleRef(
            id="RB-SCREW",
            version="1",
            title="2 Edelstahlschrauben (A2) je Brettende und Pfosten, vorbohren",
        ),
        RuleRef(
            id="RB-WOOD",
            version="1",
            title="Konstruktiver Holzschutz: kein Erdkontakt, Pfosten auf Platten, Kiesbett",
            norm_reference="in Anlehnung an DIN 68800-2",
        ),
        RuleRef(
            id="RB-REACH", version="1", title="Breite ≤ 1200 mm für beidseitige Erreichbarkeit"
        ),
        RuleRef(id="RB-FILL", version="1", title="Schichtaufbau, Erde mind. 200 mm"),
        RuleRef(id="RB-CUT", version="1", title="Zuschnitt First-Fit-Decreasing, Schnittfuge 4 mm"),
        RuleRef(
            id="RB-FOOD",
            version="1",
            title="Kein chemisch/kesseldruckbehandeltes Holz, PVC-freie Folie bei Nutzpflanzen",
        ),
    ]
}


def _guid(role: str, index: int = 0) -> UUID:
    return uuid5(_GUID_NS, f"{role}:{index}")


def _fmt_m(mm: int) -> str:
    return f"{mm / 1000:.2f}".replace(".", ",") + " m"


def _cut_lines(g: RaisedBedGeometry, wood: str) -> list[CutLine]:
    p = g.p
    board_xs = f"{BOARD_T} × {BOARD_W}"
    lines = [
        CutLine(
            part="Längsbrett",
            material=wood,
            cross_section=board_xs,
            length_mm=p.length_mm,
            count=2 * g.rows,
        ),
        CutLine(
            part="Stirnbrett",
            material=wood,
            cross_section=board_xs,
            length_mm=g.short_board_length,
            count=2 * g.rows,
        ),
        CutLine(
            part="Pfosten",
            material=wood,
            cross_section=f"{POST} × {POST}",
            length_mm=g.post_length,
            count=g.post_count,
        ),
    ]
    if p.top_cap:
        lines += [
            CutLine(
                part="Abdeckleiste lang",
                material=wood,
                cross_section=board_xs,
                length_mm=p.length_mm,
                count=2,
            ),
            CutLine(
                part="Abdeckleiste kurz",
                material=wood,
                cross_section=board_xs,
                length_mm=g.cap_short_length,
                count=2,
            ),
        ]
    if g.tie_rod_count:
        lines.append(
            CutLine(
                part="Zuganker",
                material="Edelstahl A2",
                cross_section="M10",
                length_mm=g.tie_rod_length,
                count=g.tie_rod_count,
            )
        )
    return lines


def _components(g: RaisedBedGeometry, wood: Wood) -> list[Component]:
    p = g.p
    board = Profile(thickness_mm=BOARD_T, width_mm=BOARD_W)
    post = Profile(thickness_mm=POST, width_mm=POST)
    board_mat = f"board_{wood.value}_28x145_4000"
    post_mat = f"post_{wood.value}_70x70_2500"
    comps: list[Component] = []
    for side in range(2):
        for row in range(g.rows):
            comps.append(
                Component(
                    guid=_guid("long_board", side * 100 + row),
                    ifc_type="IfcPlate",
                    role="long_board",
                    name=f"Längsbrett {'AB'[side]}{row + 1}",
                    material_id=board_mat,
                    profile=board,
                    length_mm=p.length_mm,
                )
            )
            comps.append(
                Component(
                    guid=_guid("short_board", side * 100 + row),
                    ifc_type="IfcPlate",
                    role="short_board",
                    name=f"Stirnbrett {'CD'[side]}{row + 1}",
                    material_id=board_mat,
                    profile=board,
                    length_mm=g.short_board_length,
                )
            )
    for i in range(g.post_count):
        comps.append(
            Component(
                guid=_guid("post", i),
                ifc_type="IfcMember",
                role="post",
                name=f"Pfosten P{i + 1}",
                material_id=post_mat,
                profile=post,
                length_mm=g.post_length,
            )
        )
    if p.top_cap:
        for i, length in enumerate(
            [p.length_mm, p.length_mm, g.cap_short_length, g.cap_short_length]
        ):
            comps.append(
                Component(
                    guid=_guid("cap", i),
                    ifc_type="IfcPlate",
                    role="cap",
                    name=f"Abdeckleiste K{i + 1}",
                    material_id=board_mat,
                    profile=board,
                    length_mm=length,
                )
            )
    for i in range(g.tie_rod_count):
        comps.append(
            Component(
                guid=_guid("tie_rod", i),
                ifc_type="IfcMechanicalFastener",
                role="tie_rod",
                name=f"Zuganker Z{i + 1}",
                material_id="rod_m10_a2",
                length_mm=g.tie_rod_length,
            )
        )
    if p.liner:
        comps.append(
            Component(
                guid=_guid("liner"),
                ifc_type="IfcCovering",
                role="liner",
                name="Noppenbahn innen",
                material_id=f"liner_hdpe_{g.liner_roll_width}x5000",
                length_mm=g.liner_running_length,
            )
        )
    if p.vole_mesh:
        comps.append(
            Component(
                guid=_guid("mesh"),
                ifc_type="IfcCovering",
                role="vole_mesh",
                name="Wühlmausgitter",
                material_id="mesh_galv_13mm_1000x5000",
                length_mm=g.mesh_strip_length,
                quantity=g.mesh_strips,
            )
        )
    return comps


def _notices(g: RaisedBedGeometry) -> list[Notice]:
    p = g.p
    out: list[Notice] = [
        Notice(
            code="food_safe_materials",
            severity=Severity.INFO,
            rule_id="RB-FOOD",
            message=(
                "Für Gemüse und Kräuter nur unbehandeltes Holz und PVC-freie Folie verwenden – "
                "kein kesseldruckimprägniertes oder chemisch behandeltes Holz."
            ),
        ),
        Notice(
            code="no_ground_contact",
            severity=Severity.INFO,
            rule_id="RB-WOOD",
            message=(
                "Holz nicht direkt ins Erdreich setzen: Pfosten auf Gehwegplatten stellen und "
                "unter der untersten Brettreihe ein Kiesbett vorsehen."
            ),
        ),
    ]
    if g.wall_height != p.height_mm:
        out.append(
            Notice(
                code="height_rounded",
                severity=Severity.INFO,
                rule_id="RB-ROWS",
                message=(
                    f"Die Höhe wurde auf {g.rows} ganze Brettreihen aufgerundet: "
                    f"{g.wall_height} mm statt {p.height_mm} mm."
                ),
            )
        )
    if p.width_mm > 1200:
        out.append(
            Notice(
                code="reach",
                severity=Severity.WARNING,
                rule_id="RB-REACH",
                message=(
                    "Breiter als 1,20 m ist die Beetmitte auch von beiden Seiten nur schwer "
                    "erreichbar. Für einseitigen Zugang (z. B. an einer Wand) max. ca. 0,6–0,8 m."
                ),
            )
        )
    if g.mid_count:
        out.append(
            Notice(
                code="tie_rods",
                severity=Severity.INFO,
                rule_id="RB-TIE",
                message=(
                    f"Wegen der Länge sind {g.mid_count} Zwischenpfostenpaar(e) mit "
                    f"{g.tie_rod_count} Zugankern M10 eingeplant, damit die Wände durch den Erddruck "
                    "nicht ausbauchen."
                ),
            )
        )
    if g.wall_height > HIGH_BED_FROM:
        out.append(
            Notice(
                code="high_bed",
                severity=Severity.WARNING,
                rule_id="RB-TIE",
                message=(
                    "Hohes Beet: Erddruck und Gewicht nehmen stark zu (feuchte Erde ca. 1,5–1,8 t/m³). "
                    "Nur auf ebenem, tragfähigem Untergrund aufstellen, nicht an Hängen; nicht "
                    "daraufstellen oder -setzen, außer über eine Sitzkante am Rand."
                ),
            )
        )
    if p.wood is Wood.SPRUCE:
        out.append(
            Notice(
                code="spruce_durability",
                severity=Severity.WARNING,
                rule_id="RB-WOOD",
                message=(
                    "Unbehandelte Fichte ist wenig witterungsbeständig – rechne mit wenigen Jahren "
                    "Lebensdauer. Lärche oder Douglasie halten deutlich länger."
                ),
            )
        )
    if not p.liner:
        out.append(
            Notice(
                code="no_liner",
                severity=Severity.INFO,
                message="Ohne Noppenbahn verrottet das Holz durch die feuchte Füllung schneller.",
            )
        )
    return out


def _instructions(g: RaisedBedGeometry, wood_label: str) -> list[InstructionStep]:
    p = g.p
    steps: list[tuple[str, str]] = [
        (
            "Standort und Untergrund vorbereiten",
            f"Sonnigen, ebenen Platz von ca. {_fmt_m(p.length_mm + 400)} × "
            f"{_fmt_m(p.width_mm + 400)} wählen. Grasnarbe abtragen (Soden aufbewahren), "
            f"Fläche mit der Wasserwaage abziehen. An den {g.post_count} Pfostenpositionen "
            "Gehwegplatten 30 × 30 cm bündig und waagerecht in ein Splitt- oder Sandbett setzen; "
            "unter den Wänden einen schmalen Kiesstreifen anlegen.",
        ),
        (
            "Holz zuschneiden",
            f"Laut Zuschnittliste zusägen ({wood_label}). Schnittkanten entgraten. "
            "Lärche und Douglasie im Randbereich mit 3 mm vorbohren, damit nichts reißt.",
        ),
        (
            "Längswände vormontieren",
            f"Je Längswand {g.post_count // 2} Pfosten flach auslegen (Ecken bündig mit dem "
            f"Brettende, Abstand {BOARD_T} mm für das Stirnbrett). {g.rows} Längsbretter von "
            "unten nach oben aufschrauben – je Brettende und Pfosten 2 Schrauben 5 × 60 mm A2. "
            "Mit dem Winkel rechtwinklig ausrichten.",
        ),
        (
            "Kasten aufstellen",
            "Beide Längswände auf die Platten stellen und die Stirnbretter zwischen den "
            f"Längsbrettern an die Eckpfosten schrauben ({g.rows} je Seite). Diagonalen messen – "
            "sind sie gleich lang, ist der Kasten rechtwinklig.",
        ),
    ]
    if g.tie_rod_count:
        steps.append(
            (
                "Zuganker einbauen",
                f"An jedem Zwischenpfostenpaar {g.tie_levels} Loch/Löcher mit 11 mm quer durch Brett "
                f"und Pfosten bohren, Gewindestangen M10 (Länge {g.tie_rod_length} mm) einschieben "
                "und mit U-Scheiben und Muttern handfest anziehen, bis die Wände gerade stehen.",
            )
        )
    if p.vole_mesh:
        steps.append(
            (
                "Wühlmausgitter verlegen",
                f"Gitter in {g.mesh_strips} Bahn(en) à {g.mesh_strip_length} mm auf den Boden legen "
                "(10 cm Überlappung), an den Rändern ca. 10 cm hochziehen und an Brettern bzw. "
                "Pfosten festtackern.",
            )
        )
    if p.liner:
        steps.append(
            (
                "Noppenbahn anbringen",
                f"Noppenbahn ({g.liner_height} mm hoch, Noppen zum Holz) umlaufend innen an die "
                "Wände tackern, ca. 5 cm unter der Oberkante enden lassen; Stoß 20 cm überlappen. "
                "Den Boden nicht abdecken, damit Wasser abfließen kann.",
            )
        )
    if p.top_cap:
        steps.append(
            (
                "Abdeckleiste montieren",
                "Abdeckleisten flach auf die Wandoberkante legen, außen bündig ausrichten und in die "
                "Pfosten schrauben (je 2 Schrauben). Kanten leicht brechen.",
            )
        )
    layers = ", ".join(f"{layer.name} ca. {layer.thickness_mm // 10} cm" for layer in g.fill)
    steps += [
        (
            "Befüllen",
            f"Von unten nach oben befüllen: {layers}. Jede Schicht leicht andrücken und wässern. "
            f"Gesamtvolumen ca. {g.total_fill_l} l; die Füllung sackt im ersten Jahr nach.",
        ),
        (
            "Endkontrolle",
            "Alle Schrauben und Muttern prüfen, scharfe Kanten und überstehende Gewinde "
            "entschärfen (Hutmuttern oder abflexen), Wände auf Ausbauchung kontrollieren. "
            "Nach einigen Wochen Zuganker nachziehen.",
        ),
    ]
    return [InstructionStep(number=i + 1, title=t, text=x) for i, (t, x) in enumerate(steps)]


class RaisedBedPack:
    id = PACK_ID
    version = PACK_VERSION
    title = "Hochbeet aus Holz"
    description = (
        "Rechteckiges Hochbeet aus horizontalen Brettern an innenliegenden Eckpfosten, "
        "optional mit Noppenbahn, Wühlmausgitter und Sitzkante."
    )
    example_prompt = "Ich möchte ein Hochbeet 2 × 1 m, ca. 80 cm hoch, möglichst langlebig."
    params_model: type[BaseModel] = RaisedBedParams

    def variants(self, params: BaseModel) -> list[VariantSpec]:
        assert isinstance(params, RaisedBedParams)
        return [
            VariantSpec(
                key="budget",
                name="Günstig",
                description="Unbehandelte Fichte, gleiche Maße – geringste Kosten, kürzere Lebensdauer.",
                overrides={"wood": Wood.SPRUCE.value, "top_cap": False},
            ),
            VariantSpec(
                key="durable",
                name="Langlebig",
                description="Lärche, gleiche Maße – witterungsbeständiger, etwas teurer.",
                overrides={"wood": Wood.LARCH.value},
            ),
            VariantSpec(
                key="comfort",
                name="Komfort",
                description=("Douglasie, rückenschonende Arbeitshöhe ca. 90 cm mit Sitzkante."),
                overrides={"wood": Wood.DOUGLAS.value, "height_mm": 870, "top_cap": True},
            ),
        ]

    def build(self, params: BaseModel, catalog: Catalog) -> PackBuild:
        assert isinstance(params, RaisedBedParams)
        p = params
        g = compute_geometry(p)
        wood_label = WOOD_LABELS[p.wood]
        board_item = f"board_{p.wood.value}_28x145_4000"
        post_item = f"post_{p.wood.value}_70x70_2500"

        board_pieces = [p.length_mm] * (2 * g.rows) + [g.short_board_length] * (2 * g.rows)
        if p.top_cap:
            board_pieces += [p.length_mm] * 2 + [g.cap_short_length] * 2
        board_bars = plan_cuts(board_pieces, BOARD_STOCK)
        post_bars = plan_cuts([g.post_length] * g.post_count, POST_STOCK)
        stock_plan = [
            StockPlan(
                item_id=board_item,
                stock_length_mm=BOARD_STOCK,
                stock_count=len(board_bars),
                waste_mm=sum(b.waste_mm for b in board_bars),
            ),
            StockPlan(
                item_id=post_item,
                stock_length_mm=POST_STOCK,
                stock_count=len(post_bars),
                waste_mm=sum(b.waste_mm for b in post_bars),
            ),
        ]

        bom = BomBuilder(catalog)
        bom.add(board_item, len(board_bars), note=f"{len(board_pieces)} Zuschnitte")
        bom.add(post_item, len(post_bars), note=f"{g.post_count} Pfosten à {g.post_length} mm")
        screws = g.wall_screws + g.cap_screws
        bom.add("screw_a2_5x60_200", math.ceil(screws * 1.05 / 200), note=f"{screws} Stk benötigt")
        if g.tie_rod_count:
            rod_stock = 1000 if g.tie_rod_length <= 1000 else 2000
            rod_bars = plan_cuts([g.tie_rod_length] * g.tie_rod_count, rod_stock)
            bom.add(
                f"rod_m10_a2_{rod_stock}",
                len(rod_bars),
                note=f"{g.tie_rod_count} × {g.tie_rod_length} mm",
            )
            stock_plan.append(
                StockPlan(
                    item_id=f"rod_m10_a2_{rod_stock}",
                    stock_length_mm=rod_stock,
                    stock_count=len(rod_bars),
                    waste_mm=sum(b.waste_mm for b in rod_bars),
                )
            )
            bom.add("nutwasher_m10_a2_10", math.ceil(g.tie_rod_count * 2 / 10))
        bom.add("slab_concrete_300x300x40", g.post_count)
        if p.liner:
            per_roll = LINER_ROLL_LENGTH * g.liner_strips_per_roll
            bom.add(
                f"liner_hdpe_{g.liner_roll_width}x5000",
                math.ceil(g.liner_running_length / per_roll),
                note=f"{g.liner_running_length} mm Bahn à {g.liner_height} mm Höhe",
            )
        if p.liner or p.vole_mesh:
            bom.add("staples_a2_10mm_1000", 1)
        if p.vole_mesh:
            bom.add(
                "mesh_galv_13mm_1000x5000",
                math.ceil(g.mesh_strips * g.mesh_strip_length / MESH_ROLL_LENGTH),
                note=f"{g.mesh_strips} Bahn(en) à {g.mesh_strip_length} mm",
            )

        fill_layers = [
            FillLayer(
                name=layer.name,
                thickness_mm=layer.thickness_mm,
                volume_l=g.fill_volume_l(layer.thickness_mm),
                purchase=layer.purchase,
            )
            for layer in g.fill
        ]
        soil_l = sum(layer.volume_l for layer in fill_layers if layer.purchase)
        bom.add(
            "soil_raised_bed_40l",
            math.ceil(soil_l / SOIL_BAG_L),
            note=f"ca. {soil_l} l; bei großen Mengen lose Lieferung günstiger",
        )

        tool_ids = [
            "tool_drill_driver",
            "tool_saw",
            "tool_drill_bit",
            "tool_measure",
            "tool_level",
            "tool_spade",
        ]
        if p.liner or p.vole_mesh:
            tool_ids.append("tool_stapler")
        if p.vole_mesh:
            tool_ids.append("tool_snips")
        if g.tie_rod_count:
            tool_ids.append("tool_wrench")
        tool_ids.append("tool_ppe")
        tools = [Tool(name=catalog.tool(t).name) for t in tool_ids]
        tools_cost = sum_money(
            [money(catalog.tool(t).price_min, catalog.tool(t).price_max) for t in tool_ids]
        )

        key_figures = {
            "Außenmaß": f"{p.length_mm} × {p.width_mm} mm",
            "Innenmaß": f"{g.inner_length} × {g.inner_width} mm",
            "Wandhöhe": f"{g.wall_height} mm ({g.rows} Brettreihen)",
            "Gesamthöhe": f"{g.total_height} mm",
            "Holz": wood_label,
            "Pfosten": str(g.post_count),
            "Zuganker": str(g.tie_rod_count),
            "Pflanzfläche": f"{g.planting_area_m2:.2f} m²".replace(".", ","),
            "Füllvolumen": f"{g.total_fill_l} l",
        }
        summary = (
            f"Hochbeet {wood_label} {_fmt_m(p.length_mm)} × {_fmt_m(p.width_mm)}, "
            f"Höhe {_fmt_m(g.total_height)}"
        )
        return PackBuild(
            summary=summary,
            key_figures=key_figures,
            components=_components(g, p.wood),
            bom=bom.lines,
            cut_list=_cut_lines(g, wood_label),
            stock_plan=stock_plan,
            fill_layers=fill_layers,
            tools=tools,
            costs=CostSummary(
                material=bom.total(),
                tools_optional=tools_cost,
                note=(
                    "Richtpreise (Stand Katalog), ohne Lieferung. Werkzeugkosten nur, falls nichts "
                    "vorhanden ist (Leihen/Mieten oft günstiger)."
                ),
            ),
            drawings=build_drawings(g),
            instructions=_instructions(g, wood_label),
            notices=_notices(g),
            rules=list(RULES.values()),
        )


__all__ = ["PACK_ID", "PACK_VERSION", "RaisedBedPack"]
