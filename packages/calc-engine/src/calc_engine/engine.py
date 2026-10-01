"""Engine facade: pack registry, parameter validation and result assembly."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime

from construction_model.model import (
    ConstructionResult,
    ParamValue,
    ProjectInputs,
    Provenance,
    VariantSummary,
)
from pydantic import BaseModel, ValidationError

from calc_engine.catalog import Catalog, default_catalog
from calc_engine.pack import Pack, PackDescriptor

ENGINE_VERSION = "0.1.0"


class ParameterError(ValueError):
    """Invalid parameters for a pack; ``errors`` is safe to show to users and the agent."""

    def __init__(self, pack_id: str, errors: list[str]) -> None:
        super().__init__(f"Invalid parameters for '{pack_id}': " + "; ".join(errors))
        self.pack_id = pack_id
        self.errors = errors


class UnknownPackError(KeyError):
    pass


def _dump_params(params: BaseModel) -> dict[str, ParamValue]:
    return dict(params.model_dump(mode="json"))


class Engine:
    def __init__(
        self,
        packs: Iterable[Pack],
        catalog: Catalog | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._packs = {pack.id: pack for pack in packs}
        self._catalog = catalog or default_catalog()
        self._clock = clock

    @property
    def catalog(self) -> Catalog:
        return self._catalog

    def pack(self, pack_id: str) -> Pack:
        try:
            return self._packs[pack_id]
        except KeyError:
            raise UnknownPackError(pack_id) from None

    def describe_packs(self) -> list[PackDescriptor]:
        return [
            PackDescriptor(
                id=p.id,
                version=p.version,
                title=p.title,
                description=p.description,
                example_prompt=p.example_prompt,
                params_schema=p.params_model.model_json_schema(),
            )
            for p in self._packs.values()
        ]

    def validate_params(self, pack_id: str, params: Mapping[str, ParamValue]) -> BaseModel:
        pack = self.pack(pack_id)
        try:
            return pack.params_model.model_validate(dict(params))
        except ValidationError as exc:
            errors = [
                f"{'.'.join(str(p) for p in err['loc']) or 'params'}: {err['msg']}"
                for err in exc.errors()
            ]
            raise ParameterError(pack_id, errors) from None

    def variant_overrides(self, inputs: ProjectInputs) -> dict[str, dict[str, ParamValue]]:
        pack = self.pack(inputs.pack_id)
        params = self.validate_params(inputs.pack_id, inputs.params)
        return {v.key: v.overrides for v in pack.variants(params)}

    def build(self, inputs: ProjectInputs) -> ConstructionResult:
        pack = self.pack(inputs.pack_id)
        params = self.validate_params(inputs.pack_id, inputs.params)
        effective = _dump_params(params)
        built = pack.build(params, self._catalog)

        variants: list[VariantSummary] = []
        for spec in pack.variants(params):
            variant_params = self.validate_params(pack.id, {**effective, **spec.overrides})
            variant_build = pack.build(variant_params, self._catalog)
            matches = all(effective.get(k) == v for k, v in spec.overrides.items())
            variants.append(
                VariantSummary(
                    key=spec.key,
                    name=spec.name,
                    description=spec.description,
                    overrides=spec.overrides,
                    material_cost=variant_build.costs.material,
                    is_selected=inputs.variant_key == spec.key and matches,
                )
            )

        return ConstructionResult(
            summary=built.summary,
            effective_params=effective,
            key_figures=built.key_figures,
            components=built.components,
            bom=built.bom,
            cut_list=built.cut_list,
            stock_plan=built.stock_plan,
            fill_layers=built.fill_layers,
            tools=built.tools,
            costs=built.costs,
            drawings=built.drawings,
            instructions=built.instructions,
            notices=built.notices,
            variants=variants,
            provenance=Provenance(
                engine_version=ENGINE_VERSION,
                pack_id=pack.id,
                pack_version=pack.version,
                catalog_version=self._catalog.version,
                catalog_as_of=self._catalog.as_of,
                rules=built.rules,
                computed_at=self._clock(),
            ),
        )


def default_engine(clock: Callable[[], datetime] | None = None) -> Engine:
    from calc_engine.packs.raised_bed import RaisedBedPack

    if clock is None:
        return Engine([RaisedBedPack()])
    return Engine([RaisedBedPack()], clock=clock)
