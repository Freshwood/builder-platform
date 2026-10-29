"""Rules around the skeleton stage (ADR-0010): what the customer said overrides the model, and
every expression is checked against the default parameters before any module is designed."""

from __future__ import annotations

import re
from collections.abc import Mapping

from homeworking.calc_engine.assembly.expr import ExprError, evaluate, evaluate_number, is_truthy
from homeworking.calc_engine.assembly.resolve import _check_param
from homeworking.calc_engine.pipeline.blocks import prepare
from homeworking.calc_engine.pipeline.blocks.suggest import adopt, infer_support, infer_use
from homeworking.construction_model.assembly import DesignParam, Expr
from homeworking.construction_model.base import ParamValue
from homeworking.construction_model.pipeline import ModuleBrief, Skeleton, Spec

# Spec dimension -> name of the design parameter that carries it.
DIMENSION_PARAMS = {"width_mm": "width_mm", "depth_mm": "depth_mm", "height_mm": "height_mm"}

# (customer's choice, indoor or outdoor) -> catalog finish. "natural" and "paint" have no item.
_FINISHES = {
    ("oil", "indoor"): "finish_hardwax_750",
    ("oil", "outdoor"): "finish_oil_outdoor_750",
    ("glaze", "indoor"): "finish_glaze_750",
    ("glaze", "outdoor"): "finish_glaze_750",
}


_KNOWN_FINISHES = set(_FINISHES.values())


def finish_item(finish: str | None, use: str) -> str | None:
    return _FINISHES.get((finish or "", use))


def _align(param: DesignParam, value: int, *, ceiling: bool) -> DesignParam:
    low = min(param.min if param.min is not None else value, value)
    high = value if ceiling else max(param.max if param.max is not None else value, value)
    return param.model_copy(update={"default": value, "min": low, "max": high})


def _forms(value_mm: int) -> list[str]:
    """How a customer writes a length: 2500 (mm), 250 (cm), 2,5 or 2.5 (m)."""
    forms = {str(value_mm)}
    for number in (value_mm / 10, value_mm / 1000):
        text = f"{number:g}"
        forms |= {text, text.replace(".", ",")}
    return sorted(forms)


def stated(spec: Spec) -> set[str]:
    """The dimensions of the spec that the customer's own text contains. The chat model fills the
    spec and, where the customer said nothing, writes a usual value into it; such an assumption may
    be corrected by a block, a stated size may not."""
    text = spec.description.lower()
    found = set()
    for name, value in spec.dimensions().items():
        pattern = "|".join(rf"(?<![\d.,]){re.escape(f)}(?!\d)" for f in _forms(value))
        if re.search(pattern, text):
            found.add(name)
    return found


def normalize(skeleton: Skeleton, spec: Spec, *, adopt_blocks: bool = True) -> Skeleton:
    """Apply the customer's facts to the skeleton: use, support, finish and the dimensions."""
    wanted = spec.dimensions()
    params = [
        _align(p, wanted[p.name], ceiling=spec.size_mode == "max")
        if p.kind == "length" and p.name in wanted
        else p
        for p in skeleton.params
    ]
    use = spec.use or infer_use(spec.description) or skeleton.use
    # The model is told to leave the finish empty; an invented catalog id would only be rejected.
    finish = finish_item(spec.finish, use) or (
        skeleton.finish if skeleton.finish in _KNOWN_FINISHES else None
    )
    fitted = skeleton.model_copy(
        update={
            "params": params,
            "use": use,
            "support": spec.support or infer_support(spec.description) or skeleton.support,
            "finish": finish,
        }
    )
    return prepare(adopt(fitted, spec) if adopt_blocks else fitted, stated(spec))


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
    if any(m.block is not None for m in skeleton.modules):
        errors += [
            f"Ein Baustein braucht den Parameter '{name}' (kind length, Maß in mm)"
            for name in ("width_mm", "depth_mm", "height_mm")
            if name not in names
        ]
    ids = [m.id for m in skeleton.modules]
    errors += [
        f"Modul-ID '{i}' ist doppelt vergeben" for i in sorted({i for i in ids if ids.count(i) > 1})
    ]
    for module in skeleton.modules:
        errors += _module_errors(module, env)
    return errors


def default_params(skeleton: Skeleton) -> dict[str, ParamValue]:
    """The parameter values a design is checked and described with before the customer changes any."""
    return {p.name: p.default for p in skeleton.params}


def module_box(
    module: ModuleBrief, params: Mapping[str, ParamValue]
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Origin and size of a module's box in mm at the given parameter values.

    Only for skeletons that passed :func:`check_skeleton`."""

    def at(vec: tuple[Expr, Expr, Expr]) -> tuple[int, int, int]:
        x, y, z = (round(evaluate_number(v, params)) for v in vec)
        return x, y, z

    return at(module.origin), at(module.size)
