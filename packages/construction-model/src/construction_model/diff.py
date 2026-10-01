"""Human- and machine-readable difference between two engine results."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from construction_model.model import ConstructionResult, ParamValue


class ValueChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    before: ParamValue | str | None
    after: ParamValue | str | None


class QuantityChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    item_id: str
    name: str
    unit: str
    before: Decimal
    after: Decimal


class ModelDiff(BaseModel):
    model_config = ConfigDict(frozen=True)

    params: list[ValueChange]
    key_figures: list[ValueChange]
    quantities: list[QuantityChange]
    material_cost_before: tuple[Decimal, Decimal] | None
    material_cost_after: tuple[Decimal, Decimal]

    @property
    def is_empty(self) -> bool:
        return not (self.params or self.key_figures or self.quantities)


def _changes[V](before: dict[str, V], after: dict[str, V]) -> list[ValueChange]:
    out: list[ValueChange] = []
    for key in sorted(before.keys() | after.keys()):
        old, new = before.get(key), after.get(key)
        if old != new:
            out.append(ValueChange(name=key, before=old, after=new))
    return out


def diff_results(before: ConstructionResult | None, after: ConstructionResult) -> ModelDiff:
    old_lines = {line.item_id: line for line in before.bom} if before else {}
    new_lines = {line.item_id: line for line in after.bom}
    quantities: list[QuantityChange] = []
    for item_id in sorted(old_lines.keys() | new_lines.keys()):
        old, new = old_lines.get(item_id), new_lines.get(item_id)
        old_qty = old.quantity if old else Decimal(0)
        new_qty = new.quantity if new else Decimal(0)
        if old_qty != new_qty:
            ref = new or old
            assert ref is not None
            quantities.append(
                QuantityChange(
                    item_id=item_id, name=ref.name, unit=ref.unit, before=old_qty, after=new_qty
                )
            )
    return ModelDiff(
        params=_changes(dict(before.effective_params) if before else {}, after.effective_params),
        key_figures=_changes(dict(before.key_figures) if before else {}, after.key_figures),
        quantities=quantities,
        material_cost_before=(
            (before.costs.material.min, before.costs.material.max) if before else None
        ),
        material_cost_after=(after.costs.material.min, after.costs.material.max),
    )
