"""pytest plugin for ``export_goldens.py``: records engine, expression and SVG calls.

Loaded with ``-p golden_capture``. Patches the functions before the test modules are imported and
appends every call with its outcome to ``$GOLDEN_CAPTURE_DIR/*.jsonl``.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any

_DIR = Path(os.environ["GOLDEN_CAPTURE_DIR"])
_files: dict[str, Any] = {}


def _write(name: str, row: dict[str, Any]) -> None:
    fh = _files.get(name)
    if fh is None:
        fh = _files[name] = (_DIR / f"{name}.jsonl").open("a", encoding="utf-8")
    try:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
    except (TypeError, ValueError):
        pass  # values JSON cannot carry (NaN, objects) are not golden material


def _clean_env(env: Any) -> dict[str, Any] | None:
    try:
        out = {}
        for k, v in dict(env).items():
            if isinstance(v, float) and not math.isfinite(v):
                return None
            if not isinstance(v, (int, float, str, bool)):
                return None
            out[str(k)] = v
        return out
    except Exception:
        return None


def _rebind(module_prefix: str, original: Any, replacement: Any) -> None:
    for name, module in list(sys.modules.items()):
        if not name.startswith(module_prefix) or module is None:
            continue
        for attr, value in list(vars(module).items()):
            if value is original:
                setattr(module, attr, replacement)


def pytest_configure(config: Any) -> None:
    from calc_engine.assembly import expr
    from calc_engine.engine import DesignRejectedError, Engine
    from homeworking.modules.drawings import svg

    orig_build = Engine.build
    orig_validate = Engine.validate_design

    def build(self: Engine, inputs: Any) -> Any:
        dumped = inputs.model_dump(mode="json")
        try:
            result = orig_build(self, inputs)
        except DesignRejectedError as exc:
            _write("engine", {"name": "captured/build", "inputs": dumped, "errors": exc.errors})
            raise
        if self.catalog is _default_catalog():
            _write(
                "engine",
                {"name": "captured/build", "inputs": dumped, "result": result.model_dump(mode="json")},
            )
        return result

    def validate_design(self: Engine, design: Any, params: Any) -> Any:
        from construction_model.model import ProjectInputs

        try:
            return orig_validate(self, design, params)
        except DesignRejectedError as exc:
            try:
                inputs = ProjectInputs(title="validate", design=design, params=dict(params))
                _write(
                    "engine",
                    {
                        "name": "captured/validate",
                        "inputs": inputs.model_dump(mode="json"),
                        "errors": exc.errors,
                    },
                )
            except Exception:
                pass
            raise

    Engine.build = build  # type: ignore[method-assign]
    Engine.validate_design = validate_design  # type: ignore[method-assign]

    for fn_name in ("evaluate", "evaluate_number"):
        original = getattr(expr, fn_name)

        def wrapper(value: Any, env: Any, _orig: Any = original, _name: str = fn_name) -> Any:
            clean = _clean_env(env)
            try:
                out = _orig(value, env)
            except expr.ExprError as exc:
                if clean is not None:
                    _write("expr", {"fn": _name, "expr": value, "env": clean, "error": str(exc)})
                raise
            if clean is not None and not (isinstance(out, float) and not math.isfinite(out)):
                _write("expr", {"fn": _name, "expr": value, "env": clean, "value": out})
            return out

        setattr(expr, fn_name, wrapper)
        _rebind("calc_engine", original, wrapper)

    orig_render = svg.render_svg

    def render_svg(drawing: Any, *args: Any, **kwargs: Any) -> str:
        out = orig_render(drawing, *args, **kwargs)
        element_id = kwargs.get("element_id", args[0] if args else None)
        _write(
            "svg",
            {
                "name": f"captured/{drawing.view}",
                "drawing": drawing.model_dump(mode="json"),
                "element_id": element_id,
                "svg": out,
            },
        )
        return out

    svg.render_svg = render_svg
    _rebind("homeworking", orig_render, render_svg)


def _default_catalog() -> Any:
    from calc_engine.catalog import default_catalog

    return default_catalog()


def pytest_unconfigure(config: Any) -> None:
    for fh in _files.values():
        fh.close()
