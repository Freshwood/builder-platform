"""Typed commands - the only way to change a project's inputs.

Commands are produced by the UI or proposed by the agent. They are validated, applied to the
inputs and appended to the project's command log. Undo is itself a logged command; the effective
command sequence is obtained with stack semantics (:func:`effective_commands`).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from construction_model.assembly import AssemblyDesign
from construction_model.model import Note, Origin, ParamValue, ProjectInputs, Region


class CommandError(ValueError):
    """Raised when a command cannot be applied to the current inputs."""


class _Command(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CreateProject(_Command):
    type: Literal["create_project"] = "create_project"
    pack_id: str
    title: str = Field(min_length=1, max_length=200)
    params: dict[str, ParamValue] = Field(default_factory=dict)
    region: Region | None = None
    design: AssemblyDesign | None = None


class SetParameters(_Command):
    """Set one or more parameters to absolute values (lengths in mm)."""

    type: Literal["set_parameters"] = "set_parameters"
    values: dict[str, ParamValue] = Field(min_length=1)


class ChangeParameterBy(_Command):
    """Change a numeric parameter relatively, e.g. ``width_mm`` by +500."""

    type: Literal["change_parameter_by"] = "change_parameter_by"
    name: str
    delta: int


class SelectVariant(_Command):
    type: Literal["select_variant"] = "select_variant"
    variant_key: str


class Rename(_Command):
    type: Literal["rename"] = "rename"
    title: str = Field(min_length=1, max_length=200)


class SetRegion(_Command):
    type: Literal["set_region"] = "set_region"
    region: Region | None


class AddNote(_Command):
    """Attach a note. Id and timestamp live in the command so that replay is deterministic."""

    type: Literal["add_note"] = "add_note"
    text: str = Field(min_length=1, max_length=4000)
    origin: Origin = Origin.USER
    note_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReplaceDesign(_Command):
    """Replace the free-form design; keeps valid params and user notes, drops AI explanations."""

    type: Literal["replace_design"] = "replace_design"
    design: AssemblyDesign


class Undo(_Command):
    type: Literal["undo"] = "undo"


Command = Annotated[
    CreateProject
    | SetParameters
    | ChangeParameterBy
    | SelectVariant
    | Rename
    | SetRegion
    | AddNote
    | ReplaceDesign
    | Undo,
    Field(discriminator="type"),
]
"""Any command that can be stored in the command log."""

EditCommand = Annotated[
    SetParameters
    | ChangeParameterBy
    | SelectVariant
    | Rename
    | SetRegion
    | AddNote
    | ReplaceDesign,
    Field(discriminator="type"),
]
"""Commands that clients may submit for an existing project."""

command_adapter: TypeAdapter[Command] = TypeAdapter(Command)


def _still_valid(design: AssemblyDesign, name: str, value: ParamValue) -> bool:
    """Whether a parameter value can be carried over to a replaced design."""
    spec = next((p for p in design.params if p.name == name), None)
    if spec is None:
        return False
    match spec.kind:
        case "bool":
            return isinstance(value, bool)
        case "choice":
            return value in {o.value for o in spec.options}
        case _:
            if isinstance(value, bool) or not isinstance(value, int | float):
                return False
            low = spec.min if spec.min is not None else float("-inf")
            high = spec.max if spec.max is not None else float("inf")
            return low <= value <= high


def apply_to_inputs(
    inputs: ProjectInputs | None,
    command: Command,
    *,
    variant_overrides: Mapping[str, Mapping[str, ParamValue]] | None = None,
) -> ProjectInputs:
    """Apply a single (non-undo) command and return new inputs.

    Parameter values are *not* range-checked here; that is the job of the construction pack's
    parameter schema in the engine.
    """
    if isinstance(command, CreateProject):
        if inputs is not None:
            raise CommandError("Project already exists")
        return ProjectInputs(
            title=command.title,
            pack_id=command.pack_id,
            params=dict(command.params),
            region=command.region,
            design=command.design,
        )
    if inputs is None:
        raise CommandError("The first command must create the project")

    match command:
        case SetParameters(values=values):
            return inputs.model_copy(update={"params": {**inputs.params, **values}})
        case ChangeParameterBy(name=name, delta=delta):
            current = inputs.params.get(name)
            if current is None and inputs.design is not None:
                spec = next((p for p in inputs.design.params if p.name == name), None)
                current = spec.default if spec is not None else None
            if isinstance(current, bool) or not isinstance(current, int | float):
                raise CommandError(f"Parameter '{name}' is not numeric or not set")
            return inputs.model_copy(update={"params": {**inputs.params, name: current + delta}})
        case SelectVariant(variant_key=key):
            overrides = (variant_overrides or {}).get(key)
            if overrides is None:
                raise CommandError(f"Unknown variant '{key}'")
            return inputs.model_copy(
                update={"params": {**inputs.params, **overrides}, "variant_key": key}
            )
        case Rename(title=title):
            return inputs.model_copy(update={"title": title})
        case SetRegion(region=region):
            return inputs.model_copy(update={"region": region})
        case AddNote(text=text, origin=origin, note_id=note_id, created_at=created_at):
            note = Note(id=note_id, origin=origin, text=text, created_at=created_at)
            return inputs.model_copy(update={"notes": [*inputs.notes, note]})
        case ReplaceDesign(design=design):
            if inputs.design is None:
                raise CommandError("Only free-form design projects can be redesigned")
            kept = {k: v for k, v in inputs.params.items() if _still_valid(design, k, v)}
            # AI explanations describe the replaced construction; user notes stay.
            notes = [n for n in inputs.notes if n.origin is not Origin.AI]
            return inputs.model_copy(
                update={"design": design, "params": kept, "variant_key": None, "notes": notes}
            )
        case Undo():
            raise CommandError("Undo must be resolved via effective_commands()")
    raise CommandError(f"Unsupported command {command!r}")  # pragma: no cover


def effective_commands[T](log: Iterable[tuple[T, Command]]) -> list[tuple[T, Command]]:
    """Resolve undo entries with stack semantics. The create command can never be undone."""
    stack: list[tuple[T, Command]] = []
    for entry in log:
        if isinstance(entry[1], Undo):
            if len(stack) <= 1:
                raise CommandError("Nothing to undo")
            stack.pop()
        else:
            stack.append(entry)
    return stack


def can_undo(log: Sequence[Command]) -> bool:
    try:
        return len(effective_commands((None, c) for c in log)) > 1
    except CommandError:
        return False
