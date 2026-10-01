"""Construction pack interface.

A pack encapsulates the domain knowledge for one kind of construction (raised bed, terrace, ...).
It validates parameters, proposes variants and deterministically builds the construction result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

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
    StockPlan,
    Tool,
)
from pydantic import BaseModel

from calc_engine.catalog import Catalog


@dataclass(frozen=True)
class VariantSpec:
    key: str
    name: str
    description: str
    overrides: dict[str, ParamValue]


@dataclass(frozen=True)
class PackBuild:
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


class Pack(Protocol):
    id: str
    version: str
    title: str
    description: str
    params_model: type[BaseModel]
    example_prompt: str

    def variants(self, params: BaseModel) -> list[VariantSpec]: ...

    def build(self, params: BaseModel, catalog: Catalog) -> PackBuild: ...


class PackDescriptor(BaseModel):
    id: str
    version: str
    title: str
    description: str
    example_prompt: str
    params_schema: dict[str, Any]
