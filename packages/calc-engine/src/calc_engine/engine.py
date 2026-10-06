"""Engine facade: pack registry, parameter validation and result assembly."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from enum import Enum
from typing import Any, get_args

from pydantic import BaseModel, ValidationError

from calc_engine.assembly.derive import DESIGN_PACK_ID, DESIGN_PACK_VERSION, build_design
from calc_engine.assembly.resolve import DesignError, validate_params
from calc_engine.catalog import Catalog, default_catalog
from calc_engine.pack import Pack, PackBuild, PackDescriptor, VariantSpec
from calc_engine.pricing import apply_prices
from construction_model.assembly import AssemblyDesign
from construction_model.model import (
    ChoiceSpec,
    ConstructionResult,
    Origin,
    ParamSpec,
    ParamValue,
    ProjectInputs,
    Provenance,
    Trust,
    VariantSummary,
)

ENGINE_VERSION = "0.3.0"


class ParameterError(ValueError):
    """Invalid parameters for a pack; ``errors`` is safe to show to users and the agent."""

    def __init__(self, pack_id: str, errors: list[str]) -> None:
        super().__init__(f"Invalid parameters for '{pack_id}': " + "; ".join(errors))
        self.pack_id = pack_id
        self.errors = errors


class UnknownPackError(KeyError):
    pass


class DesignRejectedError(ParameterError):
    """A free-form design failed the engine checks (ADR-0004)."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__(DESIGN_PACK_ID, errors)


def _dump_params(params: BaseModel) -> dict[str, ParamValue]:
    return dict(params.model_dump(mode="json"))


def _pack_param_specs(model: type[BaseModel]) -> list[ParamSpec]:
    """UI metadata from a pack's Pydantic parameter model."""
    specs: list[ParamSpec] = []
    for name, info in model.model_fields.items():
        annotation = info.annotation
        label = info.title or name
        extra = info.json_schema_extra if isinstance(info.json_schema_extra, dict) else {}
        if annotation is bool:
            specs.append(ParamSpec(name=name, label=label, kind="bool"))
        elif isinstance(annotation, type) and issubclass(annotation, Enum):
            labels: Any = extra.get("option_labels", {})
            specs.append(
                ParamSpec(
                    name=name,
                    label=label,
                    kind="choice",
                    options=[
                        ChoiceSpec(value=str(m.value), label=str(labels.get(m.value, m.value)))
                        for m in annotation
                    ],
                )
            )
        else:
            low = high = None
            for meta in info.metadata:
                low = getattr(meta, "ge", low)
                high = getattr(meta, "le", high)
            numeric = annotation in (int, float) or set(get_args(annotation)) <= {int, float}
            if not numeric:
                continue
            specs.append(
                ParamSpec(
                    name=name,
                    label=label,
                    kind="length" if name.endswith("_mm") else "number",
                    min=low,
                    max=high,
                )
            )
    return specs


def design_param_specs(design: AssemblyDesign) -> list[ParamSpec]:
    return [
        ParamSpec(
            name=p.name,
            label=p.label,
            kind=p.kind,
            min=p.min,
            max=p.max,
            options=[ChoiceSpec(value=o.value, label=o.label) for o in p.options],
        )
        for p in design.params
    ]


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

    def pack_version(self, pack_id: str) -> str:
        if pack_id == DESIGN_PACK_ID:
            return DESIGN_PACK_VERSION
        return self.pack(pack_id).version

    def ensure_known(self, pack_id: str, design: AssemblyDesign | None) -> None:
        if pack_id == DESIGN_PACK_ID:
            if design is None:
                raise ParameterError(pack_id, ["Für freie Entwürfe fehlt der Entwurf (design)"])
            return
        if design is not None:
            raise ParameterError(pack_id, ["Ein Entwurf ist nur mit pack_id 'design' erlaubt"])
        self.pack(pack_id)

    def validate_design(
        self, design: AssemblyDesign, params: Mapping[str, ParamValue]
    ) -> dict[str, ParamValue]:
        """Validate parameters and build once, so that all engine checks run."""
        try:
            effective = validate_params(design, params)
            build_design(design, effective, self._catalog)
        except DesignError as exc:
            raise DesignRejectedError(exc.errors) from None
        return effective

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
        if inputs.design is not None:
            return {v.key: dict(v.overrides) for v in inputs.design.variants}
        pack = self.pack(inputs.pack_id)
        params = self.validate_params(inputs.pack_id, inputs.params)
        return {v.key: v.overrides for v in pack.variants(params)}

    def build(self, inputs: ProjectInputs) -> ConstructionResult:
        if inputs.design is not None:
            return self._build_design(inputs, inputs.design)
        pack = self.pack(inputs.pack_id)
        params = self.validate_params(inputs.pack_id, inputs.params)
        effective = _dump_params(params)
        built = apply_prices(pack.build(params, self._catalog), inputs.prices)

        def build_variant(spec: VariantSpec) -> PackBuild | None:
            variant_params = self.validate_params(pack.id, {**effective, **spec.overrides})
            return apply_prices(pack.build(variant_params, self._catalog), inputs.prices)

        return self._result(
            inputs,
            built,
            effective,
            pack.variants(params),
            build_variant,
            pack_id=pack.id,
            pack_version=pack.version,
            trust="pack",
            param_specs=_pack_param_specs(pack.params_model),
        )

    def _build_design(self, inputs: ProjectInputs, design: AssemblyDesign) -> ConstructionResult:
        try:
            effective = validate_params(design, inputs.params)
            built = apply_prices(build_design(design, effective, self._catalog), inputs.prices)
        except DesignError as exc:
            raise DesignRejectedError(exc.errors) from None

        def build_variant(spec: VariantSpec) -> PackBuild | None:
            try:
                params = validate_params(design, {**effective, **spec.overrides})
                return apply_prices(build_design(design, params, self._catalog), inputs.prices)
            except DesignError:
                return None

        specs = [
            VariantSpec(v.key, v.name, v.description, dict(v.overrides)) for v in design.variants
        ]
        return self._result(
            inputs,
            built,
            effective,
            specs,
            build_variant,
            pack_id=DESIGN_PACK_ID,
            pack_version=DESIGN_PACK_VERSION,
            trust="ai_draft" if design.origin == Origin.AI else "template",
            param_specs=design_param_specs(design),
        )

    def _result(
        self,
        inputs: ProjectInputs,
        built: PackBuild,
        effective: dict[str, ParamValue],
        variant_specs: list[VariantSpec],
        build_variant: Callable[[VariantSpec], PackBuild | None],
        *,
        pack_id: str,
        pack_version: str,
        trust: Trust,
        param_specs: list[ParamSpec],
    ) -> ConstructionResult:
        variants: list[VariantSummary] = []
        for spec in variant_specs:
            variant_build = build_variant(spec)
            if variant_build is None:
                continue
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
                pack_id=pack_id,
                pack_version=pack_version,
                catalog_version=self._catalog.version,
                catalog_as_of=self._catalog.as_of,
                rules=built.rules,
                computed_at=self._clock(),
            ),
            trust=trust,
            param_specs=param_specs,
            solids=built.solids,
        )


def default_engine(clock: Callable[[], datetime] | None = None) -> Engine:
    from calc_engine.packs.raised_bed import RaisedBedPack

    if clock is None:
        return Engine([RaisedBedPack()])
    return Engine([RaisedBedPack()], clock=clock)
