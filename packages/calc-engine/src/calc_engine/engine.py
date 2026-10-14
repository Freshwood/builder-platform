"""Engine facade: checks a design with its parameters and assembles the result (ADR-0008)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from calc_engine.assembly.derive import DESIGN_VERSION, build_design
from calc_engine.assembly.resolve import DesignError, validate_params
from calc_engine.build import Build, VariantSpec
from calc_engine.catalog import Catalog, default_catalog
from calc_engine.pricing import apply_prices
from construction_model.assembly import AssemblyDesign
from construction_model.model import (
    ChoiceSpec,
    ConstructionResult,
    ParamSpec,
    ParamValue,
    ProjectInputs,
    Provenance,
    VariantSummary,
)

ENGINE_VERSION = "0.4.0"


class DesignRejectedError(ValueError):
    """A design or its parameters failed the engine checks; ``errors`` is safe to show to users
    and the agent (ADR-0004)."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("Design rejected: " + "; ".join(errors))
        self.errors = errors


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
        catalog: Catalog | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._catalog = catalog or default_catalog()
        self._clock = clock

    @property
    def catalog(self) -> Catalog:
        return self._catalog

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

    def variant_overrides(self, inputs: ProjectInputs) -> dict[str, dict[str, ParamValue]]:
        return {v.key: dict(v.overrides) for v in inputs.design.variants}

    def build(self, inputs: ProjectInputs) -> ConstructionResult:
        design = inputs.design
        try:
            effective = validate_params(design, inputs.params)
            built = apply_prices(build_design(design, effective, self._catalog), inputs.prices)
        except DesignError as exc:
            raise DesignRejectedError(exc.errors) from None

        def build_variant(spec: VariantSpec) -> Build | None:
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
            param_specs=design_param_specs(design),
        )

    def _result(
        self,
        inputs: ProjectInputs,
        built: Build,
        effective: dict[str, ParamValue],
        variant_specs: list[VariantSpec],
        build_variant: Callable[[VariantSpec], Build | None],
        *,
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
                design_version=DESIGN_VERSION,
                catalog_version=self._catalog.version,
                catalog_as_of=self._catalog.as_of,
                rules=built.rules,
                computed_at=self._clock(),
            ),
            param_specs=param_specs,
            solids=built.solids,
        )


def default_engine(clock: Callable[[], datetime] | None = None) -> Engine:
    if clock is None:
        return Engine()
    return Engine(clock=clock)
