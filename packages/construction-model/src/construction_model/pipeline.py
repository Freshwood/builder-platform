"""Contracts of the staged design pipeline (ADR-0010).

A design is no longer written in one LLM call. Four stages hand over small, validated documents:

1. intake      customer input -> :class:`Spec` (the structured brief) plus :class:`Question`
2. skeleton    :class:`Spec` -> :class:`Skeleton` (parameters and modules, no geometry details)
3. modules     one :class:`ModuleDesign` per module, in module-local coordinates
4. merge       the engine joins skeleton and modules into one ``AssemblyDesign`` and checks it
5. docs        the checked design -> :class:`Documentation` (explanation and build step texts)

Every model forbids unknown fields. The LLM never produces a number that the engine derives; it
only passes on what the customer said (``Spec``) or describes parts (``ModuleDesign``).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from construction_model.assembly import (
    DesignParam,
    DesignVariant,
    Expr,
    HardwareSpec,
    JointSpec,
    PartSpec,
    Support,
    Use,
    Vec3,
)

# Short on purpose: the module id is the prefix of every merged part id (max 40 characters).
ModuleId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9]{0,11}$")]
SizeMode = Literal["exact", "approx", "max"]
Experience = Literal["beginner", "advanced", "pro"]

# Free-form "details" the customer may add in the platform settings (key -> value).
MAX_DETAILS = 20
MAX_DETAIL_CHARS = 200


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Spec(_Frozen):
    """What the customer wants to build, as far as it is known. Every field is optional except
    the description; the intake stage and the platform settings fill the rest."""

    description: str = Field(min_length=1, max_length=2000)
    use: Use | None = None
    support: Support | None = None
    width_mm: int | None = Field(None, ge=1, le=25_000)
    depth_mm: int | None = Field(None, ge=1, le=25_000)
    height_mm: int | None = Field(None, ge=1, le=15_000)
    size_mode: SizeMode = "approx"
    wood: str | None = Field(None, max_length=40)
    finish: str | None = Field(None, max_length=40)
    budget_eur: float | None = Field(None, ge=0, le=1_000_000)
    experience: Experience | None = None
    tools: list[str] = Field(default_factory=list, max_length=20)
    usage: str | None = Field(None, max_length=500)
    details: dict[str, Annotated[str, Field(max_length=MAX_DETAIL_CHARS)]] = Field(
        default_factory=dict, max_length=MAX_DETAILS
    )

    def dimensions(self) -> dict[str, int]:
        given = {"width_mm": self.width_mm, "depth_mm": self.depth_mm, "height_mm": self.height_mm}
        return {k: v for k, v in given.items() if v is not None}


class SpecUpdates(_Frozen):
    """What the intake model may read out of the customer's text: the facts, nothing else."""

    use: Use | None = None
    support: Support | None = None
    width_mm: int | None = Field(None, ge=1, le=25_000)
    depth_mm: int | None = Field(None, ge=1, le=25_000)
    height_mm: int | None = Field(None, ge=1, le=15_000)
    size_mode: SizeMode | None = None
    wood: str | None = Field(None, max_length=40)
    finish: str | None = Field(None, max_length=40)
    budget_eur: float | None = Field(None, ge=0, le=1_000_000)
    experience: Experience | None = None
    usage: str | None = Field(None, max_length=500)


class Option(_Frozen):
    value: str = Field(max_length=40)
    label: str = Field(max_length=60)


class Question(_Frozen):
    """One follow-up question. ``field`` names the :class:`Spec` field the answer fills."""

    field: str = Field(max_length=40)
    text: str = Field(min_length=1, max_length=200)
    options: list[Option] = Field(default_factory=list, max_length=8)
    blocking: bool = Field(False, description="Without an answer no design is possible")


class ModuleBrief(_Frozen):
    """A module of the skeleton: a part of the object that one small call designs on its own."""

    id: ModuleId
    title: str = Field(min_length=1, max_length=60)
    role: str = Field(min_length=1, max_length=240, description="What the module does")
    origin: Vec3 = Field(description="Global position of the module's local zero point, in mm")
    size: Vec3 = Field(description="Extent of the module's box along x, y, z, in mm")
    when: Expr | None = Field(None, description="Include the module only if this is truthy")
    interfaces: str = Field(
        "", max_length=300, description="Where and how it meets the other modules"
    )


class Skeleton(_Frozen):
    """Parameters and module layout of the object. No parts, no materials of single parts."""

    object_type: str = Field(min_length=1, max_length=60)
    summary: str = Field(max_length=200)
    category: Literal["object", "building"] = "object"
    use: Use = "indoor"
    support: Support = "floor"
    finish: str | None = None
    params: list[DesignParam] = Field(max_length=30)
    modules: list[ModuleBrief] = Field(min_length=1, max_length=12)
    variants: list[DesignVariant] = Field(default_factory=list, max_length=4)


class ModuleDesign(_Frozen):
    """The parts of one module. Positions are local: (0, 0, 0) is the module's origin."""

    module: ModuleId
    parts: list[PartSpec] = Field(min_length=1, max_length=40)
    joints: list[JointSpec] = Field(default_factory=list, max_length=15)
    hardware: list[HardwareSpec] = Field(default_factory=list, max_length=10)


class StepText(_Frozen):
    """The wording of one build step; the engine assigns the module's parts to it."""

    module: ModuleId
    title: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=800)


class Documentation(_Frozen):
    """What the documentation stage writes about a checked design. No numbers of its own."""

    explanation: str = Field(min_length=1, max_length=4000, description='"Warum so?" paragraphs')
    steps: list[StepText] = Field(default_factory=list, max_length=12)
