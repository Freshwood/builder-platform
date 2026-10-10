"""Design corpus: many constructions, one set of invariants.

The engine refuses a design that collides, floats or falls apart. That says nothing about whether
the *result* is right: a construction can pass every engine check and still have a cut list that
does not match its parts, a drawing that silently drops a board, or a cost that does not add up.
Those are the failures users actually report ("die Zeichnungen sind nicht das, was es sein soll").

So a case is a design plus parameters plus the invariants its result must satisfy. Cases come
from three sources:

- the shipped templates and packs, each swept over its parameter range,
- ``EXTRA_DESIGNS``, free-form constructions in the shapes users ask for,
- ``DESIGNS_FROM_BUGS``, regressions named after the bug report they came from.

`cases()` expands seeds over parameter combinations, so a handful of designs yields hundreds of
constructions. Every check in :func:`check` is a property the engine promises, not a snapshot:
adding a design to the corpus adds its failures, it never invalidates the others.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from calc_engine.engine import Engine, default_engine
from construction_model.assembly import AssemblyDesign
from construction_model.model import ConstructionResult, ProjectInputs

#: Orthographic views must show every part exactly once; other views are derived differently.
ORTHOGRAPHIC = frozenset({"front", "side", "plan", "back"})


@dataclass(frozen=True)
class Case:
    """One construction: a design or a pack, the parameters to build it with, and its origin."""

    name: str
    design: AssemblyDesign | None = None
    params: Mapping[str, Any] = field(default_factory=dict)
    source: str = "corpus"
    pack_id: str | None = None
    expect_rejection: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def pack(self) -> str:
        return self.pack_id or "design"


@dataclass(frozen=True)
class Violation:
    case: str
    rule: str
    detail: str


def build_result(case: Case, engine: Engine | None = None) -> ConstructionResult:
    build = (engine or default_engine()).build
    return build(
        ProjectInputs(
            title=case.name, pack_id=case.pack, params=dict(case.params), design=case.design
        )
    )


# --------------------------------------------------------------------------------------------
# Invariants
# --------------------------------------------------------------------------------------------


def _finite(value: Any, path: str, out: list[str]) -> None:
    """No NaN or infinity may reach a drawing, a cut list or a price."""
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, float) and not math.isfinite(value):
        out.append(f"{path} ist nicht endlich ({value})")
    elif isinstance(value, Mapping):
        for key, item in value.items():
            _finite(item, f"{path}.{key}", out)
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            _finite(item, f"{path}[{index}]", out)


def check(result: ConstructionResult, case: Case) -> list[Violation]:
    """Every invariant a built construction must satisfy. Empty list means it held."""
    found: list[Violation] = []

    def fail(rule: str, detail: str) -> None:
        found.append(Violation(case.name, rule, detail))

    numbers: list[str] = []
    _finite(result.cut_list, "cut_list", numbers)
    _finite(result.bom, "bom", numbers)
    _finite(result.costs.model_dump(), "costs", numbers)
    _finite([d.model_dump() for d in result.drawings], "drawings", numbers)
    for detail in numbers:
        fail("finite", detail)

    if not result.components:
        fail("components", "Ergebnis hat keine Bauteile")
    if not result.cut_list and not result.bom:
        fail("cut_list", "Weder Zuschnittliste noch Stückliste sind gefüllt")
    if not result.drawings:
        fail("drawings", "Ergebnis hat keine Zeichnung")

    for violation in _cut_lines_are_valid(result):
        fail(violation.rule, violation.detail)
    for violation in _every_part_is_accounted_for(result):
        fail(violation.rule, violation.detail)
    for violation in _cut_quantities_match(result):
        fail(violation.rule, violation.detail)
    for violation in _cut_list_matches_stock(result):
        fail(violation.rule, violation.detail)
    # Packs name their components per instance ("Längsbrett A1") while their solids are grouped,
    # so a one-to-one count only means something for a design the agent wrote itself.
    if case.design is not None:
        for violation in _every_solid_is_modelled(result):
            fail(violation.rule, violation.detail)
    for violation in _every_part_is_drawn(result, case):
        fail(violation.rule, violation.detail)
    for violation in _drawings_contain_their_parts(result):
        fail(violation.rule, violation.detail)
    for violation in _drawings_have_dimensions(result):
        fail(violation.rule, violation.detail)
    for violation in _steps_cover_every_part(result):
        fail(violation.rule, violation.detail)
    for violation in _costs_add_up(result):
        fail(violation.rule, violation.detail)
    return found


def _cut_lines_are_valid(result: ConstructionResult) -> list[Violation]:
    """Every cut line must name a real, positive piece."""
    found: list[Violation] = []
    for line in result.cut_list:
        if line.length_mm <= 0:
            found.append(Violation("", "cut_length", f"'{line.part}' hat Länge {line.length_mm}"))
        if line.count <= 0:
            found.append(Violation("", "cut_count", f"'{line.part}' hat Menge {line.count}"))
        if line.position is not None and line.position < 1:
            found.append(
                Violation("", "cut_position", f"'{line.part}' hat Position {line.position}")
            )
    return found


def _plans_for(result: ConstructionResult, material: str) -> list[Any]:
    """The stock plans a cut line of this material is cut from."""
    return [plan for plan in result.stock_plan if (plan.name or "").startswith(material)]


def _cut_list_matches_stock(result: ConstructionResult) -> list[Violation]:
    """A cut must fit the stock it is cut from, and every piece must appear in the cutting plan.

    This is what catches a cut list that no longer matches the design: the plan holds the actual
    piece lengths per bar, so a length that appears nowhere was never planned for. Bars only exist
    for linear stock, and sheet parts are the ones carrying a second cut dimension, so the bar
    check is limited to those. Matching is across all plans rather than per material, because a
    cut line names its material by display name ("Douglasie") while a plan names the same thing
    with section and length ("Kantholz Douglasie 70 × 70 mm") - there is no stable key to join on.
    """
    found: list[Violation] = []
    if not result.stock_plan:
        return found
    longest = max(float(plan.stock_length_mm) for plan in result.stock_plan)
    bars = [float(piece) for plan in result.stock_plan for bar in plan.bars for piece in bar]
    for line in result.cut_list:
        if line.length_mm > longest + 0.5:
            found.append(
                Violation(
                    "",
                    "cut_within_stock",
                    f"'{line.part}' ist {line.length_mm} mm lang, gekauft wird höchstens "
                    f"{longest:g} mm",
                )
            )
        planned = any(abs(piece - line.length_mm) <= 0.5 for piece in bars)
        if line.width_mm is None and bars and not planned:
            found.append(
                Violation(
                    "",
                    "piece_is_planned",
                    f"'{line.part}' ({line.length_mm} mm) kommt im Zuschnittplan nicht vor",
                )
            )
    for plan in result.stock_plan:
        for bar in plan.bars:
            for piece in bar:
                if float(piece) > float(plan.stock_length_mm) + 0.5:
                    found.append(
                        Violation(
                            "",
                            "bar_fits",
                            f"'{plan.name}': {piece} mm passt nicht in {plan.stock_length_mm} mm",
                        )
                    )
    return found


def _names_match(left: str, right: str) -> bool:
    """Do a cut line and a component describe the same part?

    Designs name both sides identically. Packs name the component per instance ("Längsbrett A1")
    and the cut line for the whole group ("Längsbrett"), so a prefix either way is the join.
    """
    return left == right or left.startswith(right) or right.startswith(left)


def _every_part_is_accounted_for(result: ConstructionResult) -> list[Violation]:
    """Every component must be either cut from stock or bought as a material.

    Hardware, concrete and infill are placed parts that nobody cuts; they belong in the BOM. A
    component in neither list is a part the user is told to build but cannot buy or cut.
    """
    found: list[Violation] = []
    cut_names = {line.part for line in result.cut_list}
    # BOM ids carry the stock length ("rod_m10_a2_2000"), the component carries the bare id.
    bom_items = [line.item_id for line in result.bom]
    component_names = [component.name for component in result.components]
    for component in result.components:
        if any(_names_match(component.name, cut) for cut in cut_names):
            continue
        if any(item.startswith(component.material_id) for item in bom_items):
            continue
        found.append(
            Violation(
                "",
                "part_accounted_for",
                f"'{component.name}' ({component.material_id}) steht weder in der "
                f"Zuschnittliste noch in der Stückliste",
            )
        )
    for cut in cut_names:
        if not any(_names_match(cut, name) for name in component_names):
            found.append(
                Violation("", "cut_orphans", f"'{cut}' wird zugeschnitten, gebaut wird es nie")
            )
    return found


def _cut_quantities_match(result: ConstructionResult) -> list[Violation]:
    """Where several identical parts share one cut line, the counts must add up."""
    found: list[Violation] = []
    for line in result.cut_list:
        built = sum(
            component.quantity
            for component in result.components
            if _names_match(component.name, line.part)
        )
        if built != line.count:
            found.append(
                Violation(
                    "",
                    "cut_quantity",
                    f"'{line.part}': {line.count} Zuschnitte für {built} Bauteile",
                )
            )
    return found


def _every_solid_is_modelled(result: ConstructionResult) -> list[Violation]:
    """The 3D model must contain exactly the parts the component list promises.

    This is the invariant that catches "a board is missing from the drawing": the drawings and
    the 3D view are both rendered from ``solids``, so a part that never became a solid is
    invisible in every output while the cut list still asks the user to build it.
    """
    promised = sum(component.quantity for component in result.components)
    if len(result.solids) == promised:
        return []
    return [
        Violation(
            "",
            "solids_match_components",
            f"{len(result.solids)} platzierte Bauteile für {promised} Bauteile",
        )
    ]


#: Filled shapes. Designs are drawn as projected polygons, packs as schematic rectangles.
FILLED = frozenset({"polygon", "rect"})


def _every_part_is_drawn(result: ConstructionResult, case: Case) -> list[Violation]:
    """No drawing may be blank, and a design must be drawn completely.

    Packs draw a schematic (four boards and the posts, not all thirty parts), so only the design
    path gets the exact count. There, a part without a mesh is exactly one filled polygon per
    orthographic view; shaped parts are triangulated and only material tone still works on them.
    Cut templates (``template_N``) show the sheet being cut and are left out.
    """
    found: list[Violation] = []
    if not result.solids:
        return [Violation("", "solids_present", "Das Ergebnis hat keine platzierten Bauteile")]
    tones = {solid.tone for solid in result.solids}
    meshed = any(solid.mesh is not None for solid in result.solids)
    exact = case.design is not None and not meshed
    for drawing in result.drawings:
        if drawing.view.startswith("template_"):
            continue
        filled = [p for p in drawing.primitives if p.kind in FILLED]
        if not filled:
            found.append(
                Violation("", "drawing_not_blank", f"Ansicht '{drawing.view}' ist leer")
            )
            continue
        if exact and drawing.view in ORTHOGRAPHIC and len(filled) != len(result.solids):
            found.append(
                Violation(
                    "",
                    "drawing_shows_all_parts",
                    f"Ansicht '{drawing.view}' zeigt {len(filled)} Teile, "
                    f"das Modell hat {len(result.solids)}",
                )
            )
        missing = tones - {p.tone for p in filled if p.kind == "polygon"}
        if missing and any(p.kind == "polygon" for p in filled):
            found.append(
                Violation(
                    "",
                    "drawing_shows_all_materials",
                    f"Ansicht '{drawing.view}' zeigt kein Material {sorted(missing)}",
                )
            )
    return found


def _drawings_contain_their_parts(result: ConstructionResult) -> list[Violation]:
    """No primitive may stick out of the drawing frame; a cropped board is an invisible defect."""
    found: list[Violation] = []
    for drawing in result.drawings:
        for index, primitive in enumerate(drawing.primitives):
            for x, y in _points_of(primitive):
                if not (
                    drawing.min_x - 0.5 <= x <= drawing.min_x + drawing.width + 0.5
                    and drawing.min_y - 0.5 <= y <= drawing.min_y + drawing.height + 0.5
                ):
                    found.append(
                        Violation(
                            "",
                            "drawing_contains_geometry",
                            f"Ansicht '{drawing.view}' Primitiv {index} ({primitive.kind}) "
                            f"liegt bei ({x:.0f}, {y:.0f}) außerhalb des Blatts",
                        )
                    )
                    break
    return found


def _points_of(primitive: Any) -> list[tuple[float, float]]:
    payload = primitive.model_dump()
    points = payload.get("points")
    if points:
        return [
            (float(p[0]), float(p[1])) for p in points if isinstance(p, list | tuple) and len(p) >= 2
        ]
    if payload.get("kind") == "rect":
        x, y, w, h = (float(payload[key]) for key in ("x", "y", "w", "h"))
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    return []


def _drawings_have_dimensions(result: ConstructionResult) -> list[Violation]:
    """A drawing without a single dimension cannot be built from; only cut templates may skip it."""
    found: list[Violation] = []
    for drawing in result.drawings:
        if drawing.view.startswith("template_"):
            continue
        kinds = {p.kind for p in drawing.primitives}
        if not kinds & {"dimension", "callout"}:
            found.append(
                Violation("", "drawing_has_dimensions", f"Ansicht '{drawing.view}' hat keine Maße")
            )
        if not drawing.title.strip():
            found.append(Violation("", "drawing_has_title", f"Ansicht '{drawing.view}' hat keinen Titel"))
    return found


def _steps_cover_every_part(result: ConstructionResult) -> list[Violation]:
    """Every assembly step must say something; numbers must run 1..n without gaps."""
    found: list[Violation] = []
    for index, step in enumerate(result.instructions, start=1):
        if step.number != index:
            found.append(
                Violation(
                    "",
                    "step_numbering",
                    f"Bauschritt {index} ist als Nummer {step.number} geführt",
                )
            )
        if not step.text.strip() or not step.title.strip():
            found.append(Violation("", "step_has_text", f"Bauschritt {index} ist leer"))
    return found


def _costs_add_up(result: ConstructionResult) -> list[Violation]:
    """The headline price range must be the sum of the BOM lines it summarises."""
    found: list[Violation] = []
    low = sum((line.total.min for line in result.bom), start=Decimal(0))
    high = sum((line.total.max for line in result.bom), start=Decimal(0))
    costs = result.costs.material
    if abs(low - costs.min) > Decimal("0.02") or abs(high - costs.max) > Decimal("0.02"):
        found.append(
            Violation(
                "",
                "cost_adds_up",
                f"Materialkosten {costs.min:.2f}–{costs.max:.2f} € weichen von der "
                f"Stückliste ({low:.2f}–{high:.2f} €) ab",
            )
        )
    if low > high:
        found.append(Violation("", "cost_range", "Die Stückliste ergibt eine leere Preisspanne"))
    for line in result.bom:
        if line.quantity < 0 or line.total.min < 0 or line.total.max < line.total.min:
            found.append(
                Violation("", "cost_positive", f"'{line.spec}' hat eine unbrauchbare Preisangabe")
            )
    return found


# --------------------------------------------------------------------------------------------
# Case generation
# --------------------------------------------------------------------------------------------


def _param_values(design: AssemblyDesign) -> dict[str, list[Any]]:
    """Worth testing values per parameter: the default plus both ends of the range."""
    values: dict[str, list[Any]] = {}
    for spec in design.params:
        options: list[Any] = [spec.default]
        for bound in (spec.min, spec.max):
            if bound is not None:
                options.append(int(bound) if spec.kind == "length" else bound)
        # Choice parameters have no bounds; their first and last option are the interesting ones.
        if spec.kind == "choice" and spec.options:
            options.extend([spec.options[0].value, spec.options[-1].value])
        values[spec.name] = [v for v in dict.fromkeys(options) if v is not None]
    return values


def _combinations(values: Mapping[str, list[Any]], seed: str, extra: int) -> list[dict[str, Any]]:
    """Defaults, then one parameter moved at a time, then a reproducible random sample.

    One-at-a-time covers most defects cheaply. The random sample catches defects that only appear
    when two parameters fight (a wide top on a narrow frame, say). It is seeded by name, so the
    corpus is the same on every machine and every run.
    """
    if not values:
        return [{}]
    combos: list[dict[str, Any]] = [{}]
    for name, options in values.items():
        for value in options[1:]:
            combos.append({name: value})
    rng = random.Random(seed)
    seen = {tuple(sorted(c.items())) for c in combos}
    attempts = 0
    while len(combos) < len(seen) + extra and attempts < extra * 10:
        attempts += 1
        combo = {name: rng.choice(options) for name, options in values.items()}
        key = tuple(sorted(combo.items()))
        if key in seen:
            continue
        seen.add(key)
        combos.append(combo)
    return combos


def _sample_size(design: AssemblyDesign) -> int:
    """How many random parameter combinations a design is worth.

    Building a design costs time proportional to its part count, so a 125-part house gets fewer
    random combinations than a 4-part shelf. Every parameter is still swept end to end.
    """
    parts = len(design.parts)
    if parts <= 12:
        return 10
    if parts <= 30:
        return 6
    return 3


def template_cases() -> Iterator[Case]:
    """Every shipped template, swept over its parameter range."""
    from calc_engine.assembly.templates import templates

    for key, template in sorted(templates().items()):
        design = template.design
        samples = _sample_size(design)
        for index, params in enumerate(_combinations(_param_values(design), key, extra=samples)):
            yield Case(f"template:{key}#{index}", design, params, source=f"template:{key}")


def pack_cases() -> Iterator[Case]:
    """The construction packs, swept over their parameter range."""
    for descriptor in default_engine().describe_packs():
        bounds: dict[str, list[Any]] = {}
        for name, spec in descriptor.params_schema.get("properties", {}).items():
            options = [spec.get("default")]
            options += [spec[key] for key in ("minimum", "maximum") if key in spec]
            options += list(spec.get("enum", []))
            bounds[name] = [v for v in dict.fromkeys(options) if v is not None]
        source = f"pack:{descriptor.id}"
        for index, params in enumerate(_combinations(bounds, source, extra=10)):
            yield Case(f"{source}#{index}", None, params, source=source, pack_id=descriptor.id)

