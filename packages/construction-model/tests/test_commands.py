import pytest
from construction_model.commands import (
    AddNote,
    ChangeParameterBy,
    CommandError,
    CreateProject,
    Rename,
    SelectVariant,
    SetParameters,
    Undo,
    apply_to_inputs,
    can_undo,
    command_adapter,
    effective_commands,
)
from construction_model.model import Origin, ProjectInputs


def _created() -> ProjectInputs:
    return apply_to_inputs(
        None, CreateProject(pack_id="raised_bed", title="Beet", params={"width_mm": 1000})
    )


def test_create_requires_empty_project() -> None:
    inputs = _created()
    with pytest.raises(CommandError):
        apply_to_inputs(inputs, CreateProject(pack_id="raised_bed", title="x"))


def test_first_command_must_create() -> None:
    with pytest.raises(CommandError):
        apply_to_inputs(None, Rename(title="x"))


def test_change_parameter_by_is_relative() -> None:
    inputs = apply_to_inputs(_created(), ChangeParameterBy(name="width_mm", delta=500))
    assert inputs.params["width_mm"] == 1500


def test_change_parameter_by_rejects_non_numeric() -> None:
    inputs = apply_to_inputs(_created(), SetParameters(values={"wood": "larch"}))
    with pytest.raises(CommandError):
        apply_to_inputs(inputs, ChangeParameterBy(name="wood", delta=1))
    with pytest.raises(CommandError):
        apply_to_inputs(inputs, ChangeParameterBy(name="missing", delta=1))


def test_select_variant_applies_overrides() -> None:
    overrides = {"durable": {"wood": "larch"}}
    inputs = apply_to_inputs(
        _created(), SelectVariant(variant_key="durable"), variant_overrides=overrides
    )
    assert inputs.variant_key == "durable"
    assert inputs.params["wood"] == "larch"
    with pytest.raises(CommandError):
        apply_to_inputs(inputs, SelectVariant(variant_key="nope"), variant_overrides=overrides)


def test_add_note_keeps_origin() -> None:
    inputs = apply_to_inputs(_created(), AddNote(text="Erklärung", origin=Origin.AI))
    assert inputs.notes[0].origin is Origin.AI


def test_effective_commands_resolves_undo_with_stack_semantics() -> None:
    log = [
        (1, CreateProject(pack_id="p", title="t")),
        (2, Rename(title="a")),
        (3, Rename(title="b")),
        (4, Undo()),
        (5, Rename(title="c")),
        (6, Undo()),
        (7, Undo()),
    ]
    assert [seq for seq, _ in effective_commands(log)] == [1]


def test_create_cannot_be_undone() -> None:
    log = [CreateProject(pack_id="p", title="t"), Undo()]
    with pytest.raises(CommandError):
        effective_commands(enumerate(log))  # type: ignore[arg-type]
    assert not can_undo([CreateProject(pack_id="p", title="t")])
    assert can_undo([CreateProject(pack_id="p", title="t"), Rename(title="x")])


def test_command_json_roundtrip() -> None:
    cmd = command_adapter.validate_python({"type": "change_parameter_by", "name": "w", "delta": 5})
    assert isinstance(cmd, ChangeParameterBy)
    assert command_adapter.validate_json(command_adapter.dump_json(cmd)) == cmd
