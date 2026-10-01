"""Core project model.

The project model separates *inputs* (pack, parameters, selected variant) from the *derived
result* produced by the deterministic engine. Only inputs are changed by commands; the result is
always recomputed. Lengths are integer millimetres, money is ``Decimal``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from construction_model.drawing import Drawing

SCHEMA_VERSION = 1

Mm = Annotated[int, Field(description="Length in millimetres")]
ParamValue = int | float | str | bool


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Origin(StrEnum):
    """Who produced a piece of content (relevant for AI Act Art. 50 labelling)."""

    USER = "user"
    ENGINE = "engine"
    AI = "ai"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Region(StrEnum):
    """German federal states; building regulations differ per state."""

    BW = "BW"
    BY = "BY"
    BE = "BE"
    BB = "BB"
    HB = "HB"
    HH = "HH"
    HE = "HE"
    MV = "MV"
    NI = "NI"
    NW = "NW"
    RP = "RP"
    SL = "SL"
    SN = "SN"
    ST = "ST"
    SH = "SH"
    TH = "TH"


class RuleRef(Frozen):
    """A versioned engineering rule of thumb used by the engine (provenance)."""

    id: str
    version: str
    title: str
    norm_reference: str | None = None


class Profile(Frozen):
    """Rectangular cross-section."""

    thickness_mm: Mm
    width_mm: Mm


class Component(Frozen):
    """A physical part of the construction. ``ifc_type`` eases a later IFC export."""

    guid: UUID
    ifc_type: str
    role: str
    name: str
    material_id: str
    profile: Profile | None = None
    length_mm: Mm | None = None
    quantity: int = 1


class Money(Frozen):
    min: Decimal
    max: Decimal
    currency: Literal["EUR"] = "EUR"


class BomLine(Frozen):
    position: int
    item_id: str
    name: str
    spec: str
    quantity: Decimal
    unit: str
    unit_price: Money
    total: Money
    note: str | None = None


class CutLine(Frozen):
    part: str
    material: str
    cross_section: str
    length_mm: Mm
    count: int


class StockPlan(Frozen):
    """How cut pieces are distributed over purchased stock lengths."""

    item_id: str
    stock_length_mm: Mm
    stock_count: int
    waste_mm: Mm


class Tool(Frozen):
    name: str
    required: bool = True
    note: str | None = None


class FillLayer(Frozen):
    name: str
    thickness_mm: Mm
    volume_l: int
    purchase: bool


class CostSummary(Frozen):
    material: Money
    tools_optional: Money
    note: str


class InstructionStep(Frozen):
    number: int
    title: str
    text: str
    origin: Origin = Origin.ENGINE


class Notice(Frozen):
    code: str
    severity: Severity
    message: str
    rule_id: str | None = None


class VariantSummary(Frozen):
    key: str
    name: str
    description: str
    overrides: dict[str, ParamValue]
    material_cost: Money
    is_selected: bool


class Provenance(Frozen):
    engine_version: str
    pack_id: str
    pack_version: str
    catalog_version: str
    catalog_as_of: str
    rules: list[RuleRef]
    computed_at: datetime


class ConstructionResult(Frozen):
    """Everything the engine derives from the inputs."""

    summary: str
    effective_params: dict[str, ParamValue]
    key_figures: dict[str, str]
    components: list[Component]
    bom: list[BomLine]
    cut_list: list[CutLine]
    stock_plan: list[StockPlan]
    fill_layers: list[FillLayer]
    tools: list[Tool]
    costs: CostSummary
    drawings: list[Drawing]
    instructions: list[InstructionStep]
    notices: list[Notice]
    variants: list[VariantSummary]
    provenance: Provenance


class Note(Frozen):
    """Free text attached to a project, e.g. an explanation written by the agent."""

    id: UUID = Field(default_factory=uuid4)
    origin: Origin
    text: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProjectInputs(Frozen):
    """The part of the project that commands change."""

    title: str
    pack_id: str
    params: dict[str, ParamValue]
    variant_key: str | None = None
    region: Region | None = None
    notes: list[Note] = Field(default_factory=list)


class ProjectModel(Frozen):
    """Single source of truth of a construction project."""

    schema_version: Literal[1] = 1
    id: UUID
    inputs: ProjectInputs
    result: ConstructionResult
