"""The error texts a model gets back must name the cause AND hint at the fix (in German)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from calc_engine.assembly.expr import ExprError, evaluate
from calc_engine.assembly.resolve import DesignError, resolve_parts
from construction_model.assembly import AssemblyDesign


def _param(name: str, kind: str = "length", **extra: Any) -> dict[str, Any]:
    return {"name": name, "label": name, "kind": kind, "default": 600, **extra}


def _design(
    *, when: str | None = None, params: list[dict[str, Any]] | None = None, **extra: Any
) -> AssemblyDesign:
    part: dict[str, Any] = {
        "id": "top",
        "name": "Platte",
        "material": "glulam_spruce_18",
        "size": ["width_mm", 400, 18],
        "at": [0, 0, 500],
    }
    if when is not None:
        part["when"] = when
    design: dict[str, Any] = {
        "object_type": "Tisch",
        "summary": "Tisch",
        "params": params
        or [
            _param("width_mm", min=300, max=1200),
            {
                "name": "surface",
                "label": "Fläche",
                "kind": "choice",
                "default": "boards",
                "options": [
                    {"value": "boards", "label": "Bretter"},
                    {"value": "panel", "label": "Platte"},
                ],
            },
        ],
        "parts": [part],
    }
    design.update(extra)
    return AssemblyDesign.model_validate(design)


def _resolve_errors(design: AssemblyDesign) -> list[str]:
    with pytest.raises(DesignError) as exc:
        resolve_parts(design, {"width_mm": 600, "surface": "boards"})
    return exc.value.errors


def _validation_message(**kwargs: Any) -> str:
    with pytest.raises(ValidationError) as exc:
        _design(**kwargs)
    return "; ".join(f"{e['loc']}: {e['msg']}" for e in exc.value.errors())


def test_unknown_name_with_close_match_names_the_parameter() -> None:
    (message,) = _resolve_errors(_design(when="surface_type == 'boards'"))
    assert "Unbekannter Name 'surface_type'" in message  # cause
    assert "Bauteil 'top'" in message
    assert "meintest du 'surface'?" in message  # hint
    assert "Bekannte Namen: width_mm, surface" in message  # the names that do exist


def test_unknown_name_without_match_lists_known_names() -> None:
    env = {"width_mm": 600.0, "surface": "boards", "i": 0.0, "n": 4.0}
    with pytest.raises(ExprError) as exc:
        evaluate("zzz * 2", env)
    message = str(exc.value)
    assert "Unbekannter Name 'zzz'" in message
    assert "meintest du" not in message
    assert "Bekannte Namen: width_mm, surface, i, n" in message


def test_unquoted_choice_value_is_pointed_out() -> None:
    with pytest.raises(ExprError, match=r"in Anführungszeichen schreiben: 'boards'"):
        evaluate("surface == boards", {"surface": "boards"})


def test_known_names_are_capped() -> None:
    env = {f"p{k}": 1.0 for k in range(40)}
    with pytest.raises(ExprError) as exc:
        evaluate("zzz", env)
    assert str(exc.value).endswith("p14 …")


def test_unknown_function_names_cause_and_alternatives() -> None:
    with pytest.raises(ExprError) as exc:
        evaluate("sqroot(4)", {})
    message = str(exc.value)
    assert "unbekannte Funktion sqroot()" in message
    assert "meintest du sqrt()?" in message
    assert "Erlaubt:" in message
    assert "min" in message


def test_power_operator_names_replacement() -> None:
    with pytest.raises(ExprError, match=r"Potenzen \(\*\*\) gibt es nicht.*x \* x"):
        evaluate("x ** 2", {"x": 2.0})


def test_missing_min_max_names_cause_and_example() -> None:
    message = _validation_message(params=[_param("width_mm")])
    assert "Value error, " in message  # pydantic's wrapper, the model sees it after this prefix
    assert "Parameter 'width_mm' (Art length) braucht min und max" in message  # cause
    assert '"min": 300, "max": 1200' in message  # hint
    assert "default dazwischen" in message


def test_min_greater_than_max_shows_both_values() -> None:
    message = _validation_message(params=[_param("width_mm", min=900, max=300)])
    assert "min (900) ist größer als max (300)" in message
    assert "vertauscht" in message


def test_choice_without_options_shows_the_shape() -> None:
    message = _validation_message(params=[{**_param("wood", "choice"), "default": "oak"}])
    assert "Auswahl-Parameter 'wood' braucht options" in message
    assert '"value": "oak"' in message


def test_joint_with_unknown_part_lists_existing_ids() -> None:
    message = _validation_message(joints=[{"kind": "tenon", "part": "toop", "into": "top"}])
    assert "unbekannte Bauteil-IDs: toop" in message
    assert "vorhandene IDs: top" in message


def test_duplicate_part_ids_hint_at_repeat() -> None:
    parts = _design().model_dump(mode="json")["parts"] * 2
    with pytest.raises(ValidationError) as exc:
        AssemblyDesign.model_validate({**_design().model_dump(mode="json"), "parts": parts})
    message = str(exc.value)
    assert "Doppelte Bauteil-IDs: top" in message
    assert "repeat" in message


def test_placement_error_lists_what_was_given() -> None:
    part = {"id": "top", "name": "P", "material": "glulam_spruce_18", "size": [1, 1, 1]}
    with pytest.raises(ValidationError) as exc:
        _design(parts=[part])
    message = str(exc.value)
    assert "Bauteil 'top': entweder size und at (Box) oder start und end (Stab)" in message
    assert "angegeben: size" in message
