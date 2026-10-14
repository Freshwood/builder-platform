"""Build output of the engine: everything derived from one design and its parameters."""

from __future__ import annotations

from dataclasses import dataclass, field

from construction_model.drawing import Drawing
from construction_model.model import (
    BomLine,
    Component,
    CostSummary,
    CutLine,
    FillLayer,
    InstructionStep,
    Notice,
    ParamValue,
    RuleRef,
    Solid,
    StockPlan,
    Tool,
)


@dataclass(frozen=True)
class VariantSpec:
    key: str
    name: str
    description: str
    overrides: dict[str, ParamValue]


@dataclass(frozen=True)
class Build:
    summary: str
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
    rules: list[RuleRef]
    solids: list[Solid] = field(default_factory=list)
