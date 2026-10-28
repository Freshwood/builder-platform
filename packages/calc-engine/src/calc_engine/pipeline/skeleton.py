"""Rules around the skeleton stage (ADR-0010): what the customer said overrides the model, and
every expression is checked against the default parameters before any module is designed."""

from __future__ import annotations

from collections.abc import Mapping

from calc_engine.assembly.expr import ExprError, evaluate, evaluate_number, is_truthy
from calc_engine.assembly.resolve import _check_param
from construction_model.assembly import DesignParam, Expr
from construction_model.base import ParamValue
from construction_model.pipeline import ModuleBrief, Skeleton, Spec

# Spec dimension -> name of the design parameter that carries it.
DIMENSION_PARAMS = {"width_mm": "width_mm", "depth_mm": "depth_mm", "height_mm": "height_mm"}

# (customer's choice, indoor or outdoor) -> catalog finish. "natural" and "paint" have no item.
_FINISHES = {
    ("oil", "indoor"): "finish_hardwax_750",
    ("oil", "outdoor"): "finish_oil_outdoor_750",
    ("glaze", "indoor"): "finish_glaze_750",
    ("glaze", "outdoor"): "finish_glaze_750",
}


def finish_item(finish: str | None, use: str) -> str | None:
    return _FINISHES.get((finish or "", use))


def _align(param: DesignParam, value: int, *, ceiling: bool) -> DesignParam:
    low = min(param.min if param.min is not None else value, value)
    high = value if ceiling else max(param.max if param.max is not None else value, value)
    return param.model_copy(update={"default": value, "min": low, "max": high})


def normalize(skeleton: Skeleton, spec: Spec) -> Skeleton:
    """Apply the customer's facts to the skeleton: use, support, finish and the dimensions."""
    wanted = spec.dimensions()
    params = [
        _align(p, wanted[p.name], ceiling=spec.size_mode == "max")
        if p.kind == "length" and p.name in wanted
        else p
        for p in skeleton.params
    ]
    use = spec.use or skeleton.use
    return skeleton.model_copy(
        update={
            "params": params,
            "use": use,
            "support": spec.support or skeleton.support,
            "finish": finish_item(spec.finish, use) or skeleton.finish,
        }
    )


def _env(skeleton: Skeleton) -> tuple[dict[str, ParamValue], list[str]]:
    env: dict[str, ParamValue] = {}
    errors: list[str] = []
    for param in skeleton.params:
        if param.name in env:
            errors.append(f"Parameter '{param.name}' ist doppelt vergeben")
        message = _check_param(param, param.default)
        if message:
            errors.append(f"Parameter '{param.name}': {message}")
        env[param.name] = param.default
    return env, errors


def _number(
    value: Expr, env: Mapping[str, ParamValue], where: str, errors: list[str]
) -> float | None:
    try:
        return evaluate_number(value, env)
    except ExprError as exc:
        errors.append(f"{where}: {exc}")
        return None


def _module_errors(module: ModuleBrief, env: Mapping[str, ParamValue]) -> list[str]:
    errors: list[str] = []
    for axis, value in zip("xyz", module.origin, strict=True):
        _number(value, env, f"Modul '{module.id}' origin {axis}", errors)
    for axis, value in zip("xyz", module.size, strict=True):
        extent = _number(value, env, f"Modul '{module.id}' size {axis}", errors)
        if extent is not None and extent <= 0:
            errors.append(f"Modul '{module.id}': size {axis} muss größer als 0 sein")
    if module.when is not None:
        try:
            is_truthy(evaluate(module.when, env))
        except ExprError as exc:
            errors.append(f"Modul '{module.id}' when: {exc}")
    return errors


def check_skeleton(skeleton: Skeleton, spec: Spec) -> list[str]:
    """Problems the model has to fix (empty = the skeleton is usable). Short German messages."""
    env, errors = _env(skeleton)
    names = {p.name for p in skeleton.params}
    errors += [
        f"Parameter '{name}' für die Maße des Kunden fehlt (kind length, Maße in mm)"
        for name in DIMENSION_PARAMS.values()
        if name in spec.dimensions() and name not in names
    ]
    ids = [m.id for m in skeleton.modules]
    errors += [
        f"Modul-ID '{i}' ist doppelt vergeben" for i in sorted({i for i in ids if ids.count(i) > 1})
    ]
    for module in skeleton.modules:
        errors += _module_errors(module, env)
    return errors
