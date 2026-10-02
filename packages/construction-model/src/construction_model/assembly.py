"""Parametric assembly design: the generic input format for free-form projects (ADR-0004).

A design describes *what* is built: named parameters and parts as boxes whose size and position
are expressions over those parameters. It is written by the LLM (or shipped as a template) and
stored as project input. Everything derived from it (BOM, cut list, costs, drawings) is computed
by the engine.

Coordinate system (millimetres): x to the right (width), y to the back (depth), z up (height).
The floor is z = 0. A part's ``at`` is its minimum corner (front-left-bottom) before rotation.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from construction_model.base import Origin, ParamValue

Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
Expr = Annotated[
    float | str,
    Field(
        description=(
            "Number or arithmetic expression over parameters (and the repeat variable), "
            "e.g. 'width_mm - 2 * 18' or 'i * (height_mm - 18) / (shelves - 1)'. "
            "Allowed: + - * / // % ( ), min, max, round, floor, ceil, abs, if(cond, a, b), "
            "comparisons and and/or/not."
        )
    ),
]
Vec3 = tuple[Expr, Expr, Expr]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ChoiceOption(_Frozen):
    value: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    label: str = Field(min_length=1, max_length=60)


class DesignParam(_Frozen):
    """A user-adjustable parameter. Lengths are millimetres and should end in ``_mm``."""

    name: Identifier
    label: str = Field(min_length=1, max_length=80, description="German label for the UI")
    kind: Literal["length", "count", "angle", "bool", "choice"]
    default: ParamValue
    min: float | None = None
    max: float | None = None
    options: list[ChoiceOption] = Field(
        default_factory=list, description="Only for kind=choice, e.g. wood species"
    )

    @model_validator(mode="after")
    def _check(self) -> DesignParam:
        if self.kind in {"length", "count", "angle"}:
            if self.min is None or self.max is None:
                raise ValueError(f"Parameter '{self.name}' needs min and max")
            if self.min > self.max:
                raise ValueError(f"Parameter '{self.name}': min > max")
        if self.kind == "choice" and not self.options:
            raise ValueError(f"Choice parameter '{self.name}' needs options")
        return self


class Rotation(_Frozen):
    """Rotation about an axis through the part's ``at`` point (right-hand rule)."""

    axis: Literal["x", "y", "z"]
    deg: Expr


class Repeat(_Frozen):
    """Repeat a part ``count`` times; ``var`` (0-based index) is usable in its expressions."""

    count: Expr
    var: Identifier = "i"


class PartSpec(_Frozen):
    id: Identifier
    name: str = Field(
        min_length=1, max_length=60, description="German part name, e.g. 'Seitenteil'"
    )
    material: str = Field(
        description=(
            "Catalog item id. May contain {param} placeholders for choice parameters, "
            "e.g. 'frame_{wood}_44x69'."
        ),
        max_length=80,
    )
    size: Vec3 = Field(description="Extent along x, y, z in mm")
    at: Vec3 = Field(description="Minimum corner (x, y, z) in mm before rotation")
    rotate: Rotation | None = None
    repeat: Repeat | None = None
    when: Expr | None = Field(None, description="Include the part only if this evaluates truthy")


class HardwareSpec(_Frozen):
    """Explicit hardware, e.g. hinges, castors or brackets. Screws are added automatically."""

    item: str = Field(max_length=80)
    quantity: Expr
    note: str | None = Field(None, max_length=120)
    when: Expr | None = None


class DesignStep(_Frozen):
    title: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=800)
    parts: list[Identifier] = Field(default_factory=list, description="Part ids used in this step")


class DesignVariant(_Frozen):
    key: Identifier
    name: str = Field(min_length=1, max_length=40)
    description: str = Field(max_length=200)
    overrides: dict[str, ParamValue]


class AssemblyDesign(_Frozen):
    """A complete parametric design of a buildable object."""

    object_type: str = Field(min_length=1, max_length=60, description="German, e.g. 'Wandregal'")
    summary: str = Field(
        max_length=200,
        description="One German sentence; may contain {param} placeholders",
    )
    use: Literal["indoor", "outdoor"] = "indoor"
    support: Literal["floor", "wall"] = Field(
        "floor", description="floor: stands on z=0; wall: back side (max y) is fixed to a wall"
    )
    origin: Origin = Origin.AI
    params: list[DesignParam] = Field(max_length=30)
    parts: list[PartSpec] = Field(min_length=1, max_length=120)
    hardware: list[HardwareSpec] = Field(default_factory=list, max_length=30)
    auto_screws: bool = Field(True, description="Derive screws from contact faces")
    finish: str | None = Field(None, description="Catalog item id of an oil/glaze, or null")
    steps: list[DesignStep] = Field(default_factory=list, max_length=20)
    variants: list[DesignVariant] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def _unique_ids(self) -> AssemblyDesign:
        for label, ids in (
            ("parameter", [p.name for p in self.params]),
            ("part", [p.id for p in self.parts]),
            ("variant", [v.key for v in self.variants]),
        ):
            duplicates = sorted({i for i in ids if ids.count(i) > 1})
            if duplicates:
                raise ValueError(f"Duplicate {label} ids: {', '.join(duplicates)}")
        return self
