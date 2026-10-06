"""Core project model.

The project model separates *inputs* (pack, parameters, selected variant) from the *derived
result* produced by the deterministic engine. Only inputs are changed by commands; the result is
always recomputed. Lengths are integer millimetres, money is ``Decimal``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from construction_model.assembly import AssemblyDesign
from construction_model.base import Mm, Origin, ParamValue
from construction_model.drawing import Drawing

SCHEMA_VERSION = 1

__all__ = ["Mm", "Origin", "ParamValue"]


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


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


PriceSource = Literal["estimate", "user"]


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
    price_source: PriceSource = Field(
        "estimate",
        description="estimate = catalog guide price (range), user = price entered by the user",
    )
    used_share: Decimal | None = Field(
        None,
        description="Share of the purchased quantity this project uses (e.g. 0.12 of a screw "
        "pack); None = all of it",
    )
    search_query: str = Field("", description="Search text to look the product up at retailers")


class CutLine(Frozen):
    part: str
    material: str
    cross_section: str
    length_mm: Mm
    count: int
    width_mm: Mm | None = Field(None, description="Second cut dimension for sheet parts")
    position: int | None = Field(None, description="Position number in drawings")


class StockPlan(Frozen):
    """How cut pieces are distributed over purchased stock lengths."""

    item_id: str
    stock_length_mm: Mm
    stock_count: int
    waste_mm: Mm
    name: str | None = None
    bars: list[list[Mm]] = Field(
        default_factory=list, description="Cut piece lengths per purchased bar (linear stock)"
    )
    utilization_pct: int | None = None


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
    material_used: Money | None = Field(
        None,
        description="Cost of what the project actually consumes (opened packs counted pro rata)",
    )
    user_priced: int = Field(0, description="Number of BOM lines priced by the user")


class InstructionStep(Frozen):
    number: int
    title: str
    text: str
    origin: Origin = Origin.ENGINE
    details: list[str] = Field(
        default_factory=list,
        description="Concrete sub-steps in working order (what to buy/cut, which parts, which screws)",
    )


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


class ChoiceSpec(Frozen):
    value: str
    label: str


class ParamSpec(Frozen):
    """UI metadata of an adjustable parameter (packs and designs alike)."""

    name: str
    label: str
    kind: Literal["length", "count", "angle", "bool", "choice", "number"]
    min: float | None = None
    max: float | None = None
    options: list[ChoiceSpec] = Field(default_factory=list)


class SolidRotation(Frozen):
    axis: Literal["x", "y", "z"]
    deg: float


class Solid(Frozen):
    """A placed box for 3D display. Coordinates in mm: x right, y back, z up; ``at`` = min corner."""

    position: int
    part_id: str
    name: str
    material: str
    tone: str
    size: tuple[float, float, float]
    at: tuple[float, float, float]
    rotation: SolidRotation | None = None


Trust = Literal["pack", "template", "ai_draft"]


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
    trust: Trust = "pack"
    param_specs: list[ParamSpec] = Field(default_factory=list)
    solids: list[Solid] = Field(default_factory=list)


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
    prices: dict[str, Decimal] = Field(
        default_factory=dict,
        description="Unit prices in EUR entered by the user, keyed by BOM item id",
    )
    design: AssemblyDesign | None = Field(
        None, description="Free-form parametric design (pack_id 'design', ADR-0004)"
    )


class ProjectModel(Frozen):
    """Single source of truth of a construction project."""

    schema_version: Literal[1] = 1
    id: UUID
    inputs: ProjectInputs
    result: ConstructionResult
