"""Material and tool catalog with indicative price ranges."""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from functools import cache
from importlib import resources

from construction_model.model import BomLine, Money
from pydantic import BaseModel, ConfigDict

CENT = Decimal("0.01")


class CatalogItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    spec: str
    unit: str
    price_min: Decimal
    price_max: Decimal
    category: str


class CatalogTool(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    price_min: Decimal
    price_max: Decimal


class Catalog(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    as_of: str
    note: str
    items: list[CatalogItem]
    tools: list[CatalogTool]

    def item(self, item_id: str) -> CatalogItem:
        for item in self.items:
            if item.id == item_id:
                return item
        raise KeyError(f"Catalog item '{item_id}' not found")

    def tool(self, tool_id: str) -> CatalogTool:
        for tool in self.tools:
            if tool.id == tool_id:
                return tool
        raise KeyError(f"Catalog tool '{tool_id}' not found")


@cache
def default_catalog() -> Catalog:
    raw = resources.files("calc_engine").joinpath("data/catalog.json").read_text("utf-8")
    return Catalog.model_validate(json.loads(raw))


def money(min_: Decimal, max_: Decimal) -> Money:
    return Money(min=min_.quantize(CENT, ROUND_HALF_UP), max=max_.quantize(CENT, ROUND_HALF_UP))


def sum_money(values: list[Money]) -> Money:
    return money(sum((v.min for v in values), Decimal(0)), sum((v.max for v in values), Decimal(0)))


class BomBuilder:
    """Collects BOM lines in insertion order and prices them from the catalog."""

    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog
        self._lines: list[BomLine] = []

    def add(self, item_id: str, quantity: int | Decimal, note: str | None = None) -> None:
        if quantity <= 0:
            return
        item = self._catalog.item(item_id)
        qty = Decimal(quantity)
        self._lines.append(
            BomLine(
                position=len(self._lines) + 1,
                item_id=item.id,
                name=item.name,
                spec=item.spec,
                quantity=qty,
                unit=item.unit,
                unit_price=money(item.price_min, item.price_max),
                total=money(item.price_min * qty, item.price_max * qty),
                note=note,
            )
        )

    @property
    def lines(self) -> list[BomLine]:
        return list(self._lines)

    def total(self) -> Money:
        return sum_money([line.total for line in self._lines])
