"""Intent check: does a built construction match what the user asked for?

The invariants in the test corpus only prove that drawings, solids, cut list and costs agree
with each other. A podium that is 400 mm too long, or one without a walkable top surface, passes
all of them. An :class:`Expectation` states what the user asked for; :func:`evaluate` checks the
built result against it. No LLM is involved: everything is derived from the engine's own output
(solids, components, BOM, parameters), so the check is deterministic and runs offline.

:func:`view_consistency` is the second half: the dimensions printed in the orthographic drawings
must equal the real extents of the solids and must agree with each other.

Loading
-------
``Expectation.model_validate(data)`` accepts plain JSON or YAML data (``extra`` fields are
rejected). An unknown feature name or an unknown feature parameter raises a ``ValidationError``
at load time; it never passes silently.

Coordinates and the envelope
----------------------------
All extents are millimetres of the overall bounding box of the *solids* (parts and placed
hardware, rotations and meshes included). The model axes are x = width (right), y = depth (back),
z = height (up). The envelope is orientation independent, like "2 m long and 1 m wide":

* ``length`` = the longer horizontal side (``max(x extent, y extent)``)
* ``width``  = the shorter horizontal side (``min(x extent, y extent)``)
* ``height`` = the z extent

Expectation fields (all optional)
---------------------------------
=================== =====================================================================
``envelope``        ``max_length_mm``, ``max_width_mm``, ``max_height_mm`` and the matching
                    ``min_*`` fields (0.5 mm rounding tolerance)
``use``             ``"indoor"`` or ``"outdoor"`` (``design.use``; designs only)
``support``         ``"floor"`` or ``"wall"`` (``design.support``; designs only)
``materials_any``   at least one component material id contains one of these substrings,
                    e.g. ``["larch"]`` (ids: ``board_larch_28x145``, ``plywood_birch_18``)
``materials_none``  no component material id contains any of these substrings, e.g.
                    ``["square_"]`` for "boards, not squared timber"
``features``        list of feature names (see below), each a string or ``{name: params}``
``parts``           ``min``/``max`` number of components (sum of component quantities)
``note``            free text (the user's request); not evaluated
=================== =====================================================================

Feature vocabulary
------------------
=================== =====================================================================
``walkable_top``    A horizontal surface at the top covers at least ``min_coverage``
                    (default 0.9) of the plan footprint (bounding rectangle of all solids).
                    The surface is the union of the plan areas of all unrotated box parts
                    whose top face lies on one level (1 mm tolerance). The highest level in
                    ``[min_height_mm, max_height_mm]`` that is covered enough counts. Unless
                    ``allow_above`` is true, nothing may rise above it. Born from the kids'
                    catwalk podium (boards or panel).
``choice_param``    ``"choice_param:<name>=<v1>|<v2>"`` or ``{"choice_param": {"name": ...,
                    "values": [...]}}``. The design has that choice parameter, it offers all
                    values, and EVERY listed value builds (no engine rejection) and still
                    meets the geometric rules: envelope, ``use``, ``support`` and the other
                    features. Materials and part counts are checked for the base build only,
                    because they legitimately differ per option. Needs ``engine``.
``hinged_doors``    Every door or wing has at least ``min_hinges`` (default 2) hinges. Hinges
                    are BOM lines whose catalog hardware type is ``hinge`` (placed parts and
                    plain hardware alike). Wings: ``wings`` parameter of the feature, else
                    the effective design parameter ``wings``/``doors``/``leaves``, else 1.
                    The check is on the total (wings * min_hinges); the BOM does not assign
                    a hinge to a wing.
``standing_stable`` The construction stands on the floor: it is not wall mounted, the lowest
                    point is at z = 0, the volume-weighted centre (boxes, uniform density)
                    lies inside the bounding rectangle of the floor-contact parts, and
                    ``height / short side of that rectangle <= max_height_ratio`` (default 4)
                    unless the BOM holds a wall anchor (tip-over protection).
``levels``          At least ``min`` distinct horizontal levels (shelves, seats, tops) each
                    cover at least ``min_coverage`` (default 0.5) of the footprint.
``contoured``       At least ``min`` (default 1) parts have a non-box contour (mesh): cloud,
                    arch, rounded or cut-out shapes.
=================== =====================================================================

Example (the podium from docs/problems/bug.md)::

    {
      "envelope": {"max_length_mm": 2000, "max_width_mm": 1000},
      "use": "indoor",
      "support": "floor",
      "features": [{"walkable_top": {"min_coverage": 0.9}},
                   "choice_param:surface=boards|panel"]
    }

Messages are German, one :class:`Violation` (rule id plus detail) each; an empty list means the
intent is met.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from calc_engine.engine import DesignRejectedError, Engine, default_engine
from construction_model.assembly import Support, Use
from construction_model.drawing import Dimension
from construction_model.model import ConstructionResult, ProjectInputs, Solid

Vec = tuple[float, float, float]

#: Tolerance of limits and comparisons: dimension texts are rounded to whole millimetres.
TOL_MM = 0.5
#: Two level heights closer than this are one level.
_LEVEL_TOL_MM = 1.0
#: Tolerance between a printed dimension and the solids (text rounding plus solid rounding).
_VIEW_TOL_MM = 1.0
ORTHOGRAPHIC_AXES: dict[str, tuple[int, int]] = {
    "front": (0, 2),
    "side": (1, 2),
    "plan": (0, 1),
    "back": (0, 2),
}
_AXIS_NAME = "xyz"


@dataclass(frozen=True)
class Violation:
    """One unmet expectation or inconsistency: a stable rule id and a German detail."""

    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.detail}"


# --------------------------------------------------------------------------------------------
# Expectation model
# --------------------------------------------------------------------------------------------


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Envelope(_Model):
    """Limits of the overall bounding box; see the module docstring for the axis definition."""

    max_length_mm: float | None = Field(None, gt=0)
    max_width_mm: float | None = Field(None, gt=0)
    max_height_mm: float | None = Field(None, gt=0)
    min_length_mm: float | None = Field(None, gt=0)
    min_width_mm: float | None = Field(None, gt=0)
    min_height_mm: float | None = Field(None, gt=0)


class PartCount(_Model):
    min: int | None = Field(None, ge=0)
    max: int | None = Field(None, ge=0)


class WalkableTop(_Model):
    min_coverage: float = Field(0.9, gt=0, le=1)
    min_height_mm: float | None = Field(None, ge=0)
    max_height_mm: float | None = Field(None, ge=0)
    allow_above: bool = False


class ChoiceParam(_Model):
    name: str = Field(min_length=1)
    values: list[str] = Field(min_length=1)


class HingedDoors(_Model):
    wings: int | None = Field(None, ge=1)
    min_hinges: int = Field(2, ge=1)


class StandingStable(_Model):
    max_height_ratio: float = Field(4.0, gt=0)


class Levels(_Model):
    min: int = Field(ge=1)
    min_coverage: float = Field(0.5, gt=0, le=1)


class Contoured(_Model):
    min: int = Field(1, ge=1)


FEATURE_PARAMS: dict[str, type[_Model]] = {
    "walkable_top": WalkableTop,
    "choice_param": ChoiceParam,
    "hinged_doors": HingedDoors,
    "standing_stable": StandingStable,
    "levels": Levels,
    "contoured": Contoured,
}


class Feature(_Model):
    """A named feature with validated parameters (``params`` is the parameter model's dump)."""

    name: str
    params: dict[str, Any] = Field(default_factory=dict)

    def parsed(self) -> _Model:
        return FEATURE_PARAMS[self.name].model_validate(self.params)


def _feature_from(raw: Any) -> Feature:
    """Normalise ``"name"``, ``"choice_param:n=a|b"``, ``{name: params}`` and ``Feature`` data."""
    if isinstance(raw, Feature):
        return raw
    name: str
    params: Any
    if isinstance(raw, str):
        name, _, arg = raw.partition(":")
        name = name.strip()
        params = {}
        if arg:
            if name != "choice_param":
                raise ValueError(f"Merkmal '{name}' kennt keine Kurzform mit ':' ('{raw}')")
            param, eq, options = arg.partition("=")
            values = [v.strip() for v in options.split("|") if v.strip()]
            if not eq or not param.strip() or not values:
                raise ValueError(
                    f"Ungültiges Merkmal '{raw}': erwartet 'choice_param:<name>=<wert1>|<wert2>'"
                )
            params = {"name": param.strip(), "values": values}
    elif isinstance(raw, Mapping):
        if set(raw) == {"name", "params"}:
            name, params = str(raw["name"]), raw["params"]
        elif len(raw) == 1:
            ((key, params),) = raw.items()
            name = str(key)
        else:
            raise ValueError(
                f"Ein Merkmal ist genau ein Name oder {{name: parameter}}, nicht {dict(raw)}"
            )
    else:
        raise ValueError(f"Merkmal muss ein Text oder {{name: parameter}} sein, nicht {raw!r}")
    spec = FEATURE_PARAMS.get(name)
    if spec is None:
        known = ", ".join(sorted(FEATURE_PARAMS))
        raise ValueError(f"Unbekanntes Merkmal '{name}'. Bekannt: {known}")
    if params is None or params is True:
        params = {}
    if not isinstance(params, Mapping):
        raise ValueError(f"Parameter von Merkmal '{name}' müssen ein Objekt sein, nicht {params!r}")
    try:
        validated = spec.model_validate(dict(params))
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors()
        )
        raise ValueError(f"Merkmal '{name}': {problems}") from None
    return Feature(name=name, params=validated.model_dump(exclude_unset=True))


class Expectation(_Model):
    """What the user asked for. Every field is optional; see the module docstring."""

    envelope: Envelope | None = None
    use: Use | None = None
    support: Support | None = None
    materials_any: list[str] = Field(default_factory=list)
    materials_none: list[str] = Field(default_factory=list)
    features: list[Feature] = Field(default_factory=list)
    parts: PartCount | None = None
    note: str | None = None

    @field_validator("features", mode="before")
    @classmethod
    def _features(cls, value: Any) -> Any:
        if not isinstance(value, list | tuple):
            raise ValueError("features muss eine Liste sein")
        return [_feature_from(item) for item in value]


# --------------------------------------------------------------------------------------------
# Geometry of the result
# --------------------------------------------------------------------------------------------


def _rotate(p: Vec, pivot: Vec, axis: str, deg: float) -> Vec:
    rad = math.radians(deg)
    c, s = math.cos(rad), math.sin(rad)
    x, y, z = p[0] - pivot[0], p[1] - pivot[1], p[2] - pivot[2]
    if axis == "x":
        y, z = y * c - z * s, y * s + z * c
    elif axis == "y":
        x, z = x * c + z * s, -x * s + z * c
    else:
        x, y = x * c - y * s, x * s + y * c
    return (x + pivot[0], y + pivot[1], z + pivot[2])


def solid_bounds(solid: Solid) -> tuple[Vec, Vec]:
    """Axis-aligned bounds (min corner, max corner) of a solid in world coordinates."""
    if solid.mesh is not None and solid.mesh.vertices:
        points: list[Vec] = [(v[0], v[1], v[2]) for v in solid.mesh.vertices]
    else:
        at, size = solid.at, solid.size
        points = [
            (at[0] + dx * size[0], at[1] + dy * size[1], at[2] + dz * size[2])
            for dx in (0, 1)
            for dy in (0, 1)
            for dz in (0, 1)
        ]
        if solid.rotation is not None:
            points = [_rotate(p, at, solid.rotation.axis, solid.rotation.deg) for p in points]
    return (
        (min(p[0] for p in points), min(p[1] for p in points), min(p[2] for p in points)),
        (max(p[0] for p in points), max(p[1] for p in points), max(p[2] for p in points)),
    )


def bounding_box(solids: list[Solid]) -> tuple[Vec, Vec] | None:
    """Overall bounds of all solids, or None without solids."""
    if not solids:
        return None
    bounds = [solid_bounds(s) for s in solids]
    return (
        (
            min(b[0][0] for b in bounds),
            min(b[0][1] for b in bounds),
            min(b[0][2] for b in bounds),
        ),
        (
            max(b[1][0] for b in bounds),
            max(b[1][1] for b in bounds),
            max(b[1][2] for b in bounds),
        ),
    )


def _extents(box: tuple[Vec, Vec]) -> Vec:
    return (box[1][0] - box[0][0], box[1][1] - box[0][1], box[1][2] - box[0][2])


def _size_text(extent: Vec) -> str:
    """Overall size as ``length × width × height`` (module docstring) for messages."""
    length, width = max(extent[0], extent[1]), min(extent[0], extent[1])
    return f"{round(length)} × {round(width)} × {round(extent[2])} mm (Länge × Breite × Höhe)"


# --------------------------------------------------------------------------------------------
# evaluate
# --------------------------------------------------------------------------------------------


def evaluate(
    inputs: ProjectInputs,
    result: ConstructionResult,
    expectation: Expectation,
    engine: Engine | None = None,
) -> list[Violation]:
    """Violations of the expectation by the built result; an empty list means intent met.

    ``engine`` is only needed for ``choice_param`` (it rebuilds the construction per option);
    the default engine is used when omitted.
    """
    found = _check_geometric(inputs, result, expectation, engine)
    found += _check_material_and_parts(result, expectation)
    for feature in expectation.features:
        if feature.name == "choice_param":
            found += _choice_param(inputs, result, expectation, feature, engine)
    return found


def _check_geometric(
    inputs: ProjectInputs,
    result: ConstructionResult,
    expectation: Expectation,
    engine: Engine | None,
) -> list[Violation]:
    """Rules that depend on shape and placement only (also applied to every choice option)."""
    found: list[Violation] = []
    if expectation.envelope is not None:
        found += _envelope(result, expectation.envelope)
    if expectation.use is not None:
        found += _declared(inputs, "use", expectation.use, "Nutzung")
    if expectation.support is not None:
        found += _declared(inputs, "support", expectation.support, "Aufstellung")
    for feature in expectation.features:
        check = _FEATURE_CHECKS.get(feature.name)
        if check is not None:
            found += check(inputs, result, feature.parsed(), engine)
    return found


def _envelope(result: ConstructionResult, env: Envelope) -> list[Violation]:
    box = bounding_box(result.solids)
    if box is None:
        return [
            Violation("envelope", "Das Ergebnis hat keine Körper, die Außenmaße sind unbekannt")
        ]
    extent = _extents(box)
    measured = {
        "length": max(extent[0], extent[1]),
        "width": min(extent[0], extent[1]),
        "height": extent[2],
    }
    labels = {"length": "Länge", "width": "Breite", "height": "Höhe"}
    found: list[Violation] = []
    for axis, value in measured.items():
        upper: float | None = getattr(env, f"max_{axis}_mm")
        lower: float | None = getattr(env, f"min_{axis}_mm")
        if upper is not None and value > upper + TOL_MM:
            found.append(
                Violation(
                    f"envelope.max_{axis}",
                    f"{labels[axis]} {round(value)} mm überschreitet das Maximum von "
                    f"{round(upper)} mm (Außenmaße {_size_text(extent)})",
                )
            )
        if lower is not None and value < lower - TOL_MM:
            found.append(
                Violation(
                    f"envelope.min_{axis}",
                    f"{labels[axis]} {round(value)} mm unterschreitet das Minimum von "
                    f"{round(lower)} mm (Außenmaße {_size_text(extent)})",
                )
            )
    return found


def _declared(inputs: ProjectInputs, field: str, wanted: str, label: str) -> list[Violation]:
    actual = getattr(inputs.design, field)
    if actual != wanted:
        return [Violation(field, f"{label} ist '{actual}', gewünscht war '{wanted}'")]
    return []


def _check_material_and_parts(
    result: ConstructionResult, expectation: Expectation
) -> list[Violation]:
    found: list[Violation] = []
    materials = sorted({c.material_id for c in result.components})
    if expectation.materials_any and not any(
        needle in material for needle in expectation.materials_any for material in materials
    ):
        found.append(
            Violation(
                "materials_any",
                f"Kein Bauteil aus {' oder '.join(expectation.materials_any)}; "
                f"verwendet: {', '.join(materials) or 'nichts'}",
            )
        )
    for needle in expectation.materials_none:
        hits = [m for m in materials if needle in m]
        if hits:
            found.append(
                Violation(
                    "materials_none",
                    f"Unerwünschtes Material '{needle}' verwendet: {', '.join(hits)}",
                )
            )
    if expectation.parts is not None:
        count = sum(c.quantity for c in result.components)
        if expectation.parts.min is not None and count < expectation.parts.min:
            found.append(
                Violation(
                    "parts.min",
                    f"{count} Bauteile, erwartet mindestens {expectation.parts.min}",
                )
            )
        if expectation.parts.max is not None and count > expectation.parts.max:
            found.append(
                Violation(
                    "parts.max",
                    f"{count} Bauteile, erwartet höchstens {expectation.parts.max}",
                )
            )
    return found


# --- Features ---------------------------------------------------------------------------------


def _horizontal_tops(solids: list[Solid]) -> list[tuple[float, tuple[float, float, float, float]]]:
    """(top height, plan rectangle x0, y0, x1, y1) of every unrotated plain box."""
    out: list[tuple[float, tuple[float, float, float, float]]] = []
    for s in solids:
        if s.mesh is not None or s.rotation is not None:
            continue
        out.append(
            (s.at[2] + s.size[2], (s.at[0], s.at[1], s.at[0] + s.size[0], s.at[1] + s.size[1]))
        )
    return out


def _union_area(rects: list[tuple[float, float, float, float]]) -> float:
    """Area of the union of axis-aligned rectangles (coordinate compression)."""
    if not rects:
        return 0.0
    xs = sorted({r[0] for r in rects} | {r[2] for r in rects})
    ys = sorted({r[1] for r in rects} | {r[3] for r in rects})
    total = 0.0
    for x0, x1 in pairwise(xs):
        for y0, y1 in pairwise(ys):
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            if any(r[0] <= cx <= r[2] and r[1] <= cy <= r[3] for r in rects):
                total += (x1 - x0) * (y1 - y0)
    return total


def _levels(
    result: ConstructionResult,
) -> tuple[list[tuple[float, float]], float] | None:
    """Distinct horizontal levels as (height, coverage of the footprint), plus footprint area."""
    box = bounding_box(result.solids)
    if box is None:
        return None
    extent = _extents(box)
    footprint = extent[0] * extent[1]
    if footprint <= 0:
        return None
    tops = sorted(_horizontal_tops(result.solids), key=lambda t: t[0])
    clusters: list[list[tuple[float, tuple[float, float, float, float]]]] = []
    for top in tops:
        if clusters and top[0] - clusters[-1][-1][0] <= _LEVEL_TOL_MM:
            clusters[-1].append(top)
        else:
            clusters.append([top])
    levels = [
        (
            max(t[0] for t in cluster),
            min(1.0, _union_area([t[1] for t in cluster]) / footprint),
        )
        for cluster in clusters
    ]
    return levels, footprint


def _walkable_top(
    inputs: ProjectInputs, result: ConstructionResult, params: _Model, engine: Engine | None
) -> list[Violation]:
    p = _expect(params, WalkableTop)
    rule = "feature.walkable_top"
    measured = _levels(result)
    if measured is None:
        return [Violation(rule, "Ohne Körper lässt sich keine begehbare Fläche prüfen")]
    levels, _ = measured
    low = p.min_height_mm if p.min_height_mm is not None else 0.0
    high = p.max_height_mm if p.max_height_mm is not None else math.inf
    candidates = [(z, c) for z, c in levels if low - TOL_MM <= z <= high + TOL_MM]
    if not candidates:
        return [
            Violation(
                rule,
                "Keine waagerechte Fläche im Höhenbereich "
                f"{round(low)}" + ("" if math.isinf(high) else f" bis {round(high)}") + " mm",
            )
        ]
    good = [(z, c) for z, c in candidates if c >= p.min_coverage - 1e-9]
    if not good:
        z, c = max(candidates, key=lambda lc: lc[1])
        return [
            Violation(
                rule,
                f"Keine begehbare Oberfläche: die größte waagerechte Fläche (Höhe {round(z)} mm) "
                f"deckt nur {round(c * 100)} % der Grundfläche, verlangt sind "
                f"{round(p.min_coverage * 100)} %",
            )
        ]
    z, _ = max(good)
    box = bounding_box(result.solids)
    assert box is not None
    if not p.allow_above and box[1][2] > z + _LEVEL_TOL_MM:
        return [
            Violation(
                rule,
                f"Die Fläche auf {round(z)} mm ist nicht die oberste: Bauteile ragen bis "
                f"{round(box[1][2])} mm hinauf und stehen im Weg",
            )
        ]
    return []


def _levels_feature(
    inputs: ProjectInputs, result: ConstructionResult, params: _Model, engine: Engine | None
) -> list[Violation]:
    p = _expect(params, Levels)
    measured = _levels(result)
    count = 0 if measured is None else sum(1 for _, c in measured[0] if c >= p.min_coverage - 1e-9)
    if count < p.min:
        return [
            Violation(
                "feature.levels",
                f"{count} Ebenen mit mindestens {round(p.min_coverage * 100)} % Flächendeckung, "
                f"verlangt sind {p.min}",
            )
        ]
    return []


def _contoured(
    inputs: ProjectInputs, result: ConstructionResult, params: _Model, engine: Engine | None
) -> list[Violation]:
    p = _expect(params, Contoured)
    shaped = sum(1 for s in result.solids if s.mesh is not None)
    if shaped < p.min:
        return [
            Violation(
                "feature.contoured",
                f"{shaped} Bauteile mit Kontur (Form, Ausschnitt oder Schräge), verlangt sind {p.min}",
            )
        ]
    return []


def _bom_item(item_id: str) -> str:
    """BOM ids of stock material carry the stock length (``item@2500``)."""
    return item_id.partition("@")[0]


def _hinged_doors(
    inputs: ProjectInputs, result: ConstructionResult, params: _Model, engine: Engine | None
) -> list[Violation]:
    p = _expect(params, HingedDoors)
    catalog = (engine or default_engine()).catalog
    hinges = 0
    for line in result.bom:
        item = catalog.find(_bom_item(line.item_id))
        if item is not None and item.hardware_type == "hinge":
            hinges += int(line.quantity)
    wings = p.wings
    if wings is None:
        wings = next(
            (
                int(value)
                for name in ("wings", "doors", "leaves")
                if isinstance(value := result.effective_params.get(name), int | float)
                and not isinstance(value, bool)
            ),
            1,
        )
    needed = wings * p.min_hinges
    if hinges < needed:
        return [
            Violation(
                "feature.hinged_doors",
                f"{hinges} Scharniere für {wings} Flügel, nötig sind mindestens {p.min_hinges} "
                f"je Flügel, also {needed}",
            )
        ]
    return []


def _standing_stable(
    inputs: ProjectInputs, result: ConstructionResult, params: _Model, engine: Engine | None
) -> list[Violation]:
    p = _expect(params, StandingStable)
    rule = "feature.standing_stable"
    if inputs.design is not None and inputs.design.support == "wall":
        return [Violation(rule, "Das Objekt ist wandmontiert und steht nicht auf dem Boden")]
    box = bounding_box(result.solids)
    if box is None:
        return [Violation(rule, "Ohne Körper lässt sich die Standsicherheit nicht prüfen")]
    if abs(box[0][2]) > _LEVEL_TOL_MM:
        return [
            Violation(
                rule, f"Der tiefste Punkt liegt bei {round(box[0][2])} mm, nicht auf dem Boden"
            )
        ]
    feet = [s for s in result.solids if solid_bounds(s)[0][2] <= _LEVEL_TOL_MM]
    foot_bounds = [solid_bounds(s) for s in feet]
    x0 = min(b[0][0] for b in foot_bounds)
    x1 = max(b[1][0] for b in foot_bounds)
    y0 = min(b[0][1] for b in foot_bounds)
    y1 = max(b[1][1] for b in foot_bounds)
    weights = [s.size[0] * s.size[1] * s.size[2] for s in result.solids]
    total = sum(weights)
    centres = [
        tuple((lo + hi) / 2 for lo, hi in zip(*solid_bounds(s), strict=True)) for s in result.solids
    ]
    cx = sum(w * c[0] for w, c in zip(weights, centres, strict=True)) / total
    cy = sum(w * c[1] for w, c in zip(weights, centres, strict=True)) / total
    if not (x0 - TOL_MM <= cx <= x1 + TOL_MM and y0 - TOL_MM <= cy <= y1 + TOL_MM):
        return [
            Violation(
                rule,
                f"Der Schwerpunkt ({round(cx)} / {round(cy)} mm) liegt außerhalb der Standfläche "
                f"({round(x0)}–{round(x1)} / {round(y0)}–{round(y1)} mm): Kippgefahr",
            )
        ]
    base = min(x1 - x0, y1 - y0)
    height = box[1][2]
    anchored = any("anchor" in line.item_id for line in result.bom)
    if base <= 0 or (height / base > p.max_height_ratio and not anchored):
        return [
            Violation(
                rule,
                f"Höhe {round(height)} mm bei einer Standfläche von nur {round(base)} mm "
                f"(Verhältnis {height / base if base > 0 else math.inf:.1f}, erlaubt "
                f"{p.max_height_ratio:g}) und ohne Wandbefestigung",
            )
        ]
    return []


def _expect[T: _Model](params: _Model, kind: type[T]) -> T:
    assert isinstance(params, kind)
    return params


_FEATURE_CHECKS: dict[
    str, Callable[[ProjectInputs, ConstructionResult, _Model, Engine | None], list[Violation]]
] = {
    "walkable_top": _walkable_top,
    "hinged_doors": _hinged_doors,
    "standing_stable": _standing_stable,
    "levels": _levels_feature,
    "contoured": _contoured,
}


def _choice_param(
    inputs: ProjectInputs,
    result: ConstructionResult,
    expectation: Expectation,
    feature: Feature,
    engine: Engine | None,
) -> list[Violation]:
    """The parameter exists with these options and every option builds and keeps the geometry."""
    p = _expect(feature.parsed(), ChoiceParam)
    rule = "feature.choice_param"
    engine = engine or default_engine()
    base = result
    spec = next((s for s in base.param_specs if s.name == p.name), None)
    if spec is None or spec.kind != "choice":
        return [Violation(rule, f"Der Entwurf hat keinen Auswahlparameter '{p.name}'")]
    offered = [o.value for o in spec.options]
    missing = [v for v in p.values if v not in offered]
    if missing:
        return [
            Violation(
                rule,
                f"Auswahlparameter '{p.name}' bietet {', '.join(missing)} nicht an "
                f"(vorhanden: {', '.join(offered)})",
            )
        ]
    # Geometry and features of the option; materials and part counts differ per option by design.
    per_option = expectation.model_copy(
        update={
            "materials_any": [],
            "materials_none": [],
            "parts": None,
            "features": [f for f in expectation.features if f.name != "choice_param"],
        }
    )
    found: list[Violation] = []
    for value in p.values:
        if base.effective_params.get(p.name) == value:
            continue  # the base build above is this option; do not report its findings twice
        variant = inputs.model_copy(update={"params": {**inputs.params, p.name: value}})
        try:
            built = engine.build(variant)
        except DesignRejectedError as error:
            found.append(
                Violation(
                    rule, f"{p.name}={value} lässt sich nicht bauen: {'; '.join(error.errors)}"
                )
            )
            continue
        for violation in _check_geometric(variant, built, per_option, engine):
            found.append(Violation(violation.rule, f"[{p.name}={value}] {violation.detail}"))
    return found


# --------------------------------------------------------------------------------------------
# view_consistency
# --------------------------------------------------------------------------------------------

_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")
_SIZE_IN_TEXT = re.compile(r"(\d+) × (\d+) × (\d+) mm")


def _dimension_value(text: str) -> float | None:
    return float(text) if _NUMBER.match(text.strip()) else None


def view_consistency(result: ConstructionResult) -> list[Violation]:
    """Printed dimensions versus the solids, and the views versus each other.

    Orthographic views (front, side, plan, back) carry two overall dimensions (horizontal first,
    vertical second) followed by a chain of level dimensions along the vertical edge. The check:

    * each overall dimension text equals the solids' bounding box extent on that axis,
    * the dimension line's own coordinates span the same length as its text,
    * the level chain adds up to the overall height of the solids,
    * the same axis reads the same in every view (width in front = width in plan, ...),
    * the size in each view description and in the key figure ``Außenmaße`` agrees.

    The engine derives the texts from the solids' bounds, so a clean result is expected; the
    check exists to catch a regression or a tampered result.
    """
    box = bounding_box(result.solids)
    if box is None:
        return [Violation("view.solids", "Ohne Körper lassen sich die Ansichten nicht prüfen")]
    extent = _extents(box)
    found: list[Violation] = []
    printed: dict[int, list[tuple[str, float]]] = {0: [], 1: [], 2: []}

    for drawing in result.drawings:
        axes = ORTHOGRAPHIC_AXES.get(drawing.view)
        if axes is not None:
            found += _check_ortho_view(drawing.view, drawing.primitives, axes, extent, box, printed)
        match = _SIZE_IN_TEXT.search(drawing.description)
        if match and not drawing.view.startswith("template_"):
            stated = tuple(float(g) for g in match.groups())
            for axis in range(3):
                if abs(stated[axis] - extent[axis]) > _VIEW_TOL_MM:
                    found.append(
                        Violation(
                            "view.description",
                            f"Beschreibung von '{drawing.view}' nennt {_AXIS_LABEL[axis]} "
                            f"{round(stated[axis])} mm, die Körper messen {round(extent[axis])} mm",
                        )
                    )

    for axis, entries in printed.items():
        for (view_a, value_a), (view_b, value_b) in pairwise(entries):
            if abs(value_a - value_b) > _VIEW_TOL_MM:
                found.append(
                    Violation(
                        "view.cross",
                        f"{_AXIS_LABEL[axis]} in '{view_a}' ({round(value_a)} mm) und in "
                        f"'{view_b}' ({round(value_b)} mm) stimmen nicht überein",
                    )
                )

    key = result.key_figures.get("Außenmaße (B × T × H)")
    if key is not None:
        match = _SIZE_IN_TEXT.search(key)
        if match:
            stated = tuple(float(g) for g in match.groups())
            for axis in range(3):
                if abs(stated[axis] - extent[axis]) > _VIEW_TOL_MM:
                    found.append(
                        Violation(
                            "view.key_figure",
                            f"Kennzahl 'Außenmaße' nennt {_AXIS_LABEL[axis]} "
                            f"{round(stated[axis])} mm, die Körper messen {round(extent[axis])} mm",
                        )
                    )
    return found


_AXIS_LABEL = {0: "Breite (x)", 1: "Tiefe (y)", 2: "Höhe (z)"}


def _check_ortho_view(
    view: str,
    primitives: list[Any],
    axes: tuple[int, int],
    extent: Vec,
    box: tuple[Vec, Vec],
    printed: dict[int, list[tuple[str, float]]],
) -> list[Violation]:
    dims = [p for p in primitives if isinstance(p, Dimension)]
    if len(dims) < 2:
        return [Violation("view.dimensions", f"Ansicht '{view}' hat weniger als zwei Maßlinien")]
    found: list[Violation] = []
    overall = [
        (dims[0], axes[0], abs(dims[0].x2 - dims[0].x1)),
        (dims[1], axes[1], abs(dims[1].y2 - dims[1].y1)),
    ]
    for dim, axis, span in overall:
        value = _dimension_value(dim.text)
        label = _AXIS_LABEL[axis]
        if value is None:
            found.append(
                Violation("view.dimensions", f"Maß '{dim.text}' in '{view}' ist keine Zahl")
            )
            continue
        printed[axis].append((view, value))
        if abs(value - extent[axis]) > _VIEW_TOL_MM:
            found.append(
                Violation(
                    "view.dimension",
                    f"Ansicht '{view}' zeigt {label} {dim.text} mm, die Körper messen "
                    f"{round(extent[axis])} mm",
                )
            )
        if abs(span - value) > _VIEW_TOL_MM:
            found.append(
                Violation(
                    "view.dimension_line",
                    f"Maßlinie für {label} in '{view}' ist {round(span)} mm lang, beschriftet "
                    f"mit {dim.text} mm",
                )
            )
    chain = dims[2:]
    if chain:
        values = [_dimension_value(d.text) for d in chain]
        if any(v is None for v in values):
            found.append(
                Violation("view.dimensions", f"Höhenkette in '{view}' enthält Nichtzahlen")
            )
        else:
            total = sum(v for v in values if v is not None)
            top = box[1][axes[1]]
            if abs(total - top) > _VIEW_TOL_MM * len(chain):
                found.append(
                    Violation(
                        "view.chain",
                        f"Höhenkette in '{view}' summiert sich auf {round(total)} mm, die "
                        f"Oberkante liegt bei {round(top)} mm",
                    )
                )
    return found


__all__ = [
    "FEATURE_PARAMS",
    "Envelope",
    "Expectation",
    "Feature",
    "PartCount",
    "Violation",
    "bounding_box",
    "evaluate",
    "solid_bounds",
    "view_consistency",
]
