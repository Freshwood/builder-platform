"""The error texts a model gets back must name the cause AND hint at the fix (in German)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from calc_engine.assembly.expr import ExprError, evaluate
from calc_engine.assembly.resolve import DesignError, resolve_parts
from calc_engine.engine import DesignRejectedError, default_engine
from construction_model.assembly import AssemblyDesign
from construction_model.model import ProjectInputs


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


# --- Engine checks (check.py): the message must say which dimension is off and the way out -------


def _build_errors(*parts: dict[str, Any], support: str = "floor") -> str:
    design = AssemblyDesign.model_validate(
        {
            "object_type": "Podest",
            "summary": "Podest",
            "support": support,
            "params": [],
            "parts": list(parts),
        }
    )
    inputs = ProjectInputs(title="t", params={}, design=design)
    with pytest.raises(DesignRejectedError) as exc:
        default_engine().build(inputs)
    return " | ".join(exc.value.errors)


def _part(pid: str, material: str, size: list[Any], at: list[Any]) -> dict[str, Any]:
    return {"id": pid, "name": pid, "material": material, "size": size, "at": at}


def test_section_mismatch_names_dimension_and_made_to_order_id() -> None:
    """The production case (run 615963ad): 70 mm strips on a 44 x 69 mm section."""
    message = _build_errors(_part("rahmen", "lumber_spruce_44x69", [2000, 70, 69], [0, 0, 0]))
    # The old leading words stay intact (pinned by the regression case).
    assert "passen nicht zum Querschnitt 44 × 69 mm von 'lumber_spruce_44x69'" in message
    assert "Länge 2000 mm angenommen" in message
    assert "70 → 44 mm (Stärke)" in message  # 69 already fits the width, 70 is the odd one out
    assert "Breite" not in message
    assert "Material 'lumber_spruce_69x70'" in message  # fits the written size


def test_section_mismatch_on_both_dimensions_lists_both() -> None:
    message = _build_errors(_part("rahmen", "frame_spruce_44x69", [2000, 50, 80], [0, 0, 0]))
    assert "Länge 2000 mm angenommen" in message
    assert "50 → 44 mm (Stärke)" in message
    assert "80 → 69 mm (Breite)" in message
    assert "Material 'lumber_spruce_50x80'" in message  # catalog profile: species from the item


def test_section_mismatch_never_invents_an_unavailable_id() -> None:
    # 250 mm thick is beyond the lumber rules (max 200 mm), so no id may be named.
    message = _build_errors(_part("balken", "lumber_spruce_44x69", [2000, 250, 300], [0, 0, 0]))
    assert "passen nicht zum Querschnitt 44 × 69 mm" in message
    assert "250 → 44 mm" in message
    assert "oder Material" not in message
    assert "lumber_spruce_250" not in message


def test_section_mismatch_of_non_wood_gives_no_id() -> None:
    message = _build_errors(_part("pfosten", "frame_spruce_44x44", [2000, 44, 50], [0, 0, 0]))
    assert "50 → 44 mm" in message
    assert "Material 'lumber_spruce_44x50'" in message  # a valid species cut, verified


def test_sheet_mismatch_names_nearest_thickness_and_other_board() -> None:
    message = _build_errors(_part("deck", "plywood_birch_18", [600, 400, 24], [0, 0, 0]))
    assert "kein Maß von 600 × 400 × 24 mm entspricht der Plattenstärke 18 mm" in message
    assert "weicht um 6 mm ab" in message
    assert "auf 18 mm ändern" in message
    assert "Platte 'plywood_birch_24' (24 mm) wählen" in message


def test_sheet_mismatch_without_fitting_board_lists_thicknesses() -> None:
    message = _build_errors(_part("deck", "plywood_birch_18", [600, 400, 20], [0, 0, 0]))
    assert "weicht um 2 mm ab" in message
    assert "oder Platte" not in message
    assert "lieferbare Stärken: 12, 18, 24 mm" in message


def test_piece_mismatch_names_the_deviation() -> None:
    message = _build_errors(
        _part("fuss", "foot_rubber_40", [40, 40, 12], [0, 0, 0]),
        _part("platte", "glulam_spruce_18", [40, 40, 18], [0, 0, 10]),
    )
    assert "'foot_rubber_40' hat die feste Größe 40 × 40 × 10 mm" in message
    assert "geschrieben 40 × 40 × 12 mm, Abweichung: 12 → 10 mm" in message


def test_floating_design_names_lowest_part_and_fix() -> None:
    message = _build_errors(_part("platte", "glulam_spruce_18", [400, 400, 18], [0, 0, 120]))
    assert "Kein Bauteil steht auf dem Boden (z = 0)" in message
    assert "tiefstes Teil 'platte[0]' liegt bei z = 120 mm" in message
    assert 'support="wall"' in message


def test_disconnected_group_names_gap_to_main_group() -> None:
    message = _build_errors(
        _part("a", "glulam_spruce_18", [400, 400, 18], [0, 0, 0]),
        _part("b", "glulam_spruce_18", [400, 400, 18], [0, 0, 38]),
    )
    assert "Nicht alle Bauteile sind verbunden (keine Kontaktfläche): " in message
    assert "Nächster Abstand 'b[0]' ↔ 'a[0]': Lücke z 20 mm" in message
    assert "flächig berühren" in message


def test_disconnected_group_touching_only_at_an_edge() -> None:
    message = _build_errors(
        _part("a", "glulam_spruce_18", [400, 400, 18], [0, 0, 0]),
        _part("b", "glulam_spruce_18", [400, 400, 18], [400, 400, 0]),
    )
    assert "kein flächiger Kontakt (nur Kante oder Ecke)" in message
