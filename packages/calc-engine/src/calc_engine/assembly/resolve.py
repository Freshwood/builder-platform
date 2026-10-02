"""Resolve a parametric design into concrete, placed parts (no catalog or geometry checks yet)."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass

from calc_engine.assembly.expr import ExprError, evaluate
from construction_model.assembly import AssemblyDesign, DesignParam, PartSpec
from construction_model.model import ParamValue

MAX_PARTS = 400
MAX_REPEAT = 200
_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")


class DesignError(ValueError):
    """The design cannot be built; ``errors`` are short German messages for users and the LLM."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class ResolvedPart:
    spec_id: str
    index: int
    name: str
    material: str
    size: tuple[float, float, float]
    at: tuple[float, float, float]
    rotation: tuple[str, float] | None

    @property
    def key(self) -> str:
        return f"{self.spec_id}[{self.index}]"


def _number_env(params: Mapping[str, ParamValue]) -> dict[str, float]:
    env: dict[str, float] = {}
    for name, value in params.items():
        if isinstance(value, int | float):
            env[name] = float(value)
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
    values: tuple[float | str, float | str, float | str], env: Mapping[str, float]
) -> tuple[float, float, float]:
    x, y, z = (evaluate(v, env) for v in values)
    return (x, y, z)


def resolve_parts(design: AssemblyDesign, params: Mapping[str, ParamValue]) -> list[ResolvedPart]:
    env = _number_env(params)
    errors: list[str] = []
    parts: list[ResolvedPart] = []
    for spec in design.parts:
        try:
            parts.extend(_expand(spec, env, params))
        except ExprError as exc:
            errors.append(f"Bauteil '{spec.id}': {exc}")
        if len(parts) > MAX_PARTS:
            raise DesignError([f"Mehr als {MAX_PARTS} Bauteile – Entwurf vereinfachen"])
    if errors:
        raise DesignError(errors)
    return parts


def _expand(
    spec: PartSpec, env: Mapping[str, float], params: Mapping[str, ParamValue]
) -> list[ResolvedPart]:
    count = 1
    if spec.repeat is not None:
        raw = evaluate(spec.repeat.count, env)
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
        if spec.when is not None and not evaluate(spec.when, local):
            continue
        size = _vec(spec.size, local)
        at = _vec(spec.at, local)
        if any(not math.isfinite(v) for v in (*size, *at)):
            raise ExprError("Maß ist keine endliche Zahl")
        rotation = None
        if spec.rotate is not None:
            deg = evaluate(spec.rotate.deg, local)
            if abs(deg) > 1e-9:
                rotation = (spec.rotate.axis, deg)
        out.append(
            ResolvedPart(
                spec_id=spec.id,
                index=index,
                name=spec.name,
                material=substitute(spec.material, params),
                size=(round(size[0], 1), round(size[1], 1), round(size[2], 1)),
                at=(round(at[0], 1), round(at[1], 1), round(at[2], 1)),
                rotation=rotation,
            )
        )
    return out


def resolve_quantity(expr: float | str, params: Mapping[str, ParamValue]) -> float:
    return evaluate(expr, _number_env(params))


def is_included(expr: float | str | None, params: Mapping[str, ParamValue]) -> bool:
    return expr is None or bool(evaluate(expr, _number_env(params)))
