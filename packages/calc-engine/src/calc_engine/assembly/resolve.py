"""Resolve a parametric design into concrete, placed parts (no catalog or geometry checks yet)."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass

from calc_engine.assembly.expr import ExprError, Scalar, evaluate, evaluate_number, is_truthy
from construction_model.assembly import AssemblyDesign, Cutout, DesignParam, PartSpec, Shape
from construction_model.model import ParamValue

MAX_PARTS = 400
MAX_PARTS_BUILDING = 1500
MAX_REPEAT = 200
_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")


class DesignError(ValueError):
    """The design cannot be built; ``errors`` are short German messages for users and the LLM."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


Vec3 = tuple[float, float, float]
Pt = tuple[float, float]


@dataclass(frozen=True)
class ResolvedShape:
    kind: str
    radius: float | None = None
    apex: float | None = None
    bumps: int | None = None
    points: tuple[Pt, ...] = ()


@dataclass(frozen=True)
class ResolvedCutout:
    kind: str
    at: Pt
    size: Pt
    points: tuple[Pt, ...] = ()


@dataclass(frozen=True)
class ResolvedPart:
    spec_id: str
    index: int
    name: str
    material: str
    size: Vec3
    """Box: extent along x, y, z. Member: (0, 0, 0); the engine derives it from start/end."""
    at: Vec3
    rotation: tuple[str, float] | None
    start: Vec3 | None = None
    end: Vec3 | None = None
    section: Pt | None = None
    facing: str | None = None
    cuts: tuple[str, str] = ("square", "square")
    shape: ResolvedShape | None = None
    cutouts: tuple[ResolvedCutout, ...] = ()

    @property
    def key(self) -> str:
        return f"{self.spec_id}[{self.index}]"

    @property
    def is_member(self) -> bool:
        return self.start is not None


def _param_env(params: Mapping[str, ParamValue]) -> dict[str, Scalar]:
    """Parameter values as expression environment: numbers as floats, ``choice`` values as text."""
    env: dict[str, Scalar] = {}
    for name, value in params.items():
        env[name] = value if isinstance(value, str) else float(value)
    return env


def validate_params(
    design: AssemblyDesign, params: Mapping[str, ParamValue]
) -> dict[str, ParamValue]:
    """Merge user values with defaults and check kinds and bounds."""
    specs = {p.name: p for p in design.params}
    errors = [f"{name}: unbekannter Parameter" for name in params if name not in specs]
    effective: dict[str, ParamValue] = {}
    for spec in design.params:
        value = params.get(spec.name, spec.default)
        message = _check_param(spec, value)
        if message:
            errors.append(f"{spec.name}: {message}")
            continue
        if spec.kind in {"length", "count"} and isinstance(value, float) and value.is_integer():
            value = int(value)
        effective[spec.name] = value
    if errors:
        raise DesignError(errors)
    return effective


def _check_param(spec: DesignParam, value: ParamValue) -> str | None:
    match spec.kind:
        case "bool":
            return None if isinstance(value, bool) else "muss true/false sein"
        case "choice":
            allowed = [o.value for o in spec.options]
            return None if value in allowed else f"muss eine von {', '.join(allowed)} sein"
        case _:
            if isinstance(value, bool) or not isinstance(value, int | float):
                return "muss eine Zahl sein"
            if spec.kind == "count" and not float(value).is_integer():
                return "muss ganzzahlig sein"
            assert spec.min is not None
            assert spec.max is not None
            if not spec.min <= value <= spec.max:
                return f"muss zwischen {spec.min:g} und {spec.max:g} liegen"
            return None


def substitute(template: str, params: Mapping[str, ParamValue]) -> str:
    """Replace ``{param}`` placeholders (choice parameters) in material ids and texts."""

    def repl(match: re.Match[str]) -> str:
        value = params.get(match.group(1))
        return match.group(0) if value is None else str(value)

    return _PLACEHOLDER.sub(repl, template)


def _vec(
    values: tuple[float | str, float | str, float | str], env: Mapping[str, Scalar]
) -> Vec3:
    x, y, z = (evaluate_number(v, env) for v in values)
    if not all(math.isfinite(v) for v in (x, y, z)):
        raise ExprError("Maß ist keine endliche Zahl")
    return (round(x, 1), round(y, 1), round(z, 1))


def _pt(values: tuple[float | str, float | str], env: Mapping[str, Scalar]) -> Pt:
    u, v = (evaluate_number(x, env) for x in values)
    if not all(math.isfinite(x) for x in (u, v)):
        raise ExprError("Maß ist keine endliche Zahl")
    return (round(u, 1), round(v, 1))


def _shape(shape: Shape, env: Mapping[str, Scalar]) -> ResolvedShape:
    return ResolvedShape(
        kind=shape.kind,
        radius=None if shape.radius is None else evaluate_number(shape.radius, env),
        apex=None if shape.apex is None else evaluate_number(shape.apex, env),
        bumps=shape.bumps,
        points=tuple(_pt(p, env) for p in shape.points),
    )


def _cutout(cutout: Cutout, env: Mapping[str, Scalar]) -> ResolvedCutout:
    return ResolvedCutout(
        kind=cutout.kind,
        at=_pt(cutout.at, env),
        size=_pt(cutout.size, env),
        points=tuple(_pt(p, env) for p in cutout.points),
    )


def resolve_parts(design: AssemblyDesign, params: Mapping[str, ParamValue]) -> list[ResolvedPart]:
    env = _param_env(params)
    errors: list[str] = []
    parts: list[ResolvedPart] = []
    limit = MAX_PARTS_BUILDING if design.category == "building" else MAX_PARTS
    for spec in design.parts:
        try:
            parts.extend(_expand(spec, env, params))
        except ExprError as exc:
            errors.append(f"Bauteil '{spec.id}': {exc}")
        if len(parts) > limit:
            raise DesignError([f"Mehr als {limit} Bauteile – Entwurf vereinfachen"])
    if errors:
        raise DesignError(errors)
    return parts


def _expand(
    spec: PartSpec, env: Mapping[str, Scalar], params: Mapping[str, ParamValue]
) -> list[ResolvedPart]:
    count = 1
    if spec.repeat is not None:
        raw = evaluate_number(spec.repeat.count, env)
        if not math.isfinite(raw) or raw < 0:
            raise ExprError(f"Anzahl {raw:g} ist ungültig")
        count = round(raw)
        if count > MAX_REPEAT:
            raise ExprError(f"Wiederholung {count} > {MAX_REPEAT}")
    out: list[ResolvedPart] = []
    for index in range(count):
        local = dict(env)
        if spec.repeat is not None:
            local[spec.repeat.var] = float(index)
            local["n"] = float(count)
        if spec.when is not None and not is_truthy(evaluate(spec.when, local)):
            continue
        rotation = None
        if spec.rotate is not None:
            deg = evaluate_number(spec.rotate.deg, local)
            if abs(deg) > 1e-9:
                rotation = (spec.rotate.axis, deg)
        start: Vec3 | None = None
        end: Vec3 | None = None
        if spec.start is not None and spec.end is not None:
            size: Vec3 = (0.0, 0.0, 0.0)
            at = start = _vec(spec.start, local)
            end = _vec(spec.end, local)
        else:
            if spec.cuts != ("square", "square"):
                raise ExprError("cuts gibt es nur für Stäbe mit start/end")
            assert spec.size is not None
            assert spec.at is not None
            size, at = _vec(spec.size, local), _vec(spec.at, local)
        out.append(
            ResolvedPart(
                spec_id=spec.id,
                index=index,
                name=spec.name,
                material=substitute(spec.material, params),
                size=size,
                at=at,
                rotation=rotation,
                start=start,
                end=end,
                section=None if spec.section is None else _pt(spec.section, local),
                facing=spec.facing,
                cuts=spec.cuts,
                shape=None if spec.shape is None else _shape(spec.shape, local),
                cutouts=tuple(_cutout(c, local) for c in spec.cutouts),
            )
        )
    return out


def resolve_quantity(expr: float | str, params: Mapping[str, ParamValue]) -> float:
    return evaluate_number(expr, _param_env(params))


def is_included(expr: float | str | None, params: Mapping[str, ParamValue]) -> bool:
    return expr is None or is_truthy(evaluate(expr, _param_env(params)))
