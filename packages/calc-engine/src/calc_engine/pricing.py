"""Apply the user's own prices to a build and derive the cost summary from the BOM."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal

from calc_engine.catalog import money, sum_money
from calc_engine.pack import PackBuild
from construction_model.model import BomLine


def _priced(line: BomLine, unit_price: Decimal) -> BomLine:
    return line.model_copy(
        update={
            "unit_price": money(unit_price, unit_price),
            "total": money(unit_price * line.quantity, unit_price * line.quantity),
            "price_source": "user",
        }
    )


def apply_prices(built: PackBuild, prices: Mapping[str, Decimal]) -> PackBuild:
    """Replace guide prices by user prices and recompute material and consumed cost.

    Packs build their BOM from catalog guide prices; this is the single place where user prices
    come in, so packs, designs and variants all price the same way.
    """
    bom = [
        _priced(line, prices[line.item_id]) if line.item_id in prices else line
        for line in built.bom
    ]
    used = sum_money(
        [
            money(
                line.total.min * (line.used_share if line.used_share is not None else 1),
                line.total.max * (line.used_share if line.used_share is not None else 1),
            )
            for line in bom
        ]
    )
    costs = built.costs.model_copy(
        update={
            "material": sum_money([line.total for line in bom]),
            "material_used": used,
            "user_priced": sum(1 for line in bom if line.price_source == "user"),
        }
    )
    return replace(built, bom=bom, costs=costs)
