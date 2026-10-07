"""Agent definition and tools. Tools translate LLM intents into typed project commands."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Annotated, Any
from uuid import UUID

from pydantic import BeforeValidator, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model

from calc_engine.assembly.derive import DESIGN_PACK_ID
from calc_engine.assembly.templates import template, templates
from calc_engine.catalog import Catalog
from calc_engine.engine import DesignRejectedError, Engine, ParameterError, UnknownPackError
from construction_model.assembly import AssemblyDesign
from construction_model.commands import (
    AddNote,
    ChangeParameterBy,
    CommandError,
    Rename,
    ReplaceDesign,
    SelectVariant,
    SetParameters,
    SetPrice,
    SetRegion,
)
from construction_model.diff import ModelDiff
from construction_model.model import Origin, ParamValue, ProjectModel
from homeworking.modules.agent.prompts import INSTRUCTIONS
from homeworking.modules.projects.service import ProjectNotFoundError, ProjectService


def _parse_json_string(value: Any) -> Any:
    """Accept an object argument that the model sent as a JSON-encoded string.

    Models regularly serialise large nested arguments (a whole design) into a string. Strict
    validation then rejects every attempt with "Input should be an object" and the model cannot
    see what is wrong, so the string is decoded before validation.
    """
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


_JsonTolerant = BeforeValidator(_parse_json_string)

AgentCommand = Annotated[
    SetParameters | ChangeParameterBy | SelectVariant | Rename | SetRegion | SetPrice,
    Field(discriminator="type"),
    _JsonTolerant,
]
DesignArg = Annotated[AssemblyDesign, _JsonTolerant]
ParamsArg = Annotated[dict[str, ParamValue], _JsonTolerant]


@dataclass
class AgentDeps:
    owner_id: UUID
    projects: ProjectService
    project_id: UUID | None
    trace_id: str
    changed_projects: set[UUID] = field(default_factory=set)
    # Every design the model submitted, accepted or not; stored with the agent run (it cost money).
    design_attempts: list[dict[str, Any]] = field(default_factory=list)
    # The model may call several tools in parallel; project writes must run one after another,
    # otherwise they race for the next command sequence number.
    write_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _eur(value: Any) -> str:
    return f"{value:.0f} €"


def project_summary(model: ProjectModel) -> dict[str, Any]:
    """Compact, token-friendly view of a project for the LLM."""
    r = model.result
    return {
        "project_id": str(model.id),
        "title": model.inputs.title,
        "trust": r.trust,
        "summary": r.summary,
        "params": r.effective_params,
        "adjustable": [
            {
                k: v
                for k, v in {
                    "name": p.name,
                    "label": p.label,
                    "min": p.min,
                    "max": p.max,
                    "options": [o.value for o in p.options] or None,
                }.items()
                if v is not None
            }
            for p in r.param_specs
        ],
        "key_figures": r.key_figures,
        "material_cost_eur": f"{_eur(r.costs.material.min)} – {_eur(r.costs.material.max)}",
        "material_used_eur": (
            f"{_eur(r.costs.material_used.min)} – {_eur(r.costs.material_used.max)}"
            if r.costs.material_used
            else None
        ),
        "prices": (
            f"{r.costs.user_priced} von {len(r.bom)} Positionen mit Nutzerpreis, Rest Richtpreise"
        ),
        "bom": [
            {
                "item_id": line.item_id,
                "name": f"{line.name} ({line.spec})",
                "quantity": f"{line.quantity:f} {line.unit}",
                "unit_price_eur": f"{line.unit_price.min}–{line.unit_price.max}",
                "source": line.price_source,
            }
            for line in r.bom
        ],
        "variants": [
            {
                "key": v.key,
                "name": v.name,
                "description": v.description,
                "material_cost_eur": f"{_eur(v.material_cost.min)} – {_eur(v.material_cost.max)}",
                "selected": v.is_selected,
            }
            for v in r.variants
        ],
        "notices": [n.message for n in r.notices],
    }


def diff_summary(diff: ModelDiff) -> dict[str, Any]:
    out: dict[str, Any] = {
        "changed_params": {c.name: {"before": c.before, "after": c.after} for c in diff.params},
        "changed_figures": {
            c.name: {"before": c.before, "after": c.after} for c in diff.key_figures
        },
    }
    if diff.material_cost_before:
        out["material_cost_before_eur"] = (
            f"{_eur(diff.material_cost_before[0])} – {_eur(diff.material_cost_before[1])}"
        )
    out["material_cost_after_eur"] = (
        f"{_eur(diff.material_cost_after[0])} – {_eur(diff.material_cost_after[1])}"
    )
    return out


def _error(message: str) -> dict[str, Any]:
    return {"error": message}


def _design_rejected(exc: ParameterError) -> dict[str, Any]:
    return {
        "error": "Der Entwurf wurde von der Engine abgelehnt. Korrigiere ihn und rufe das "
        "Werkzeug erneut mit dem vollständigen Entwurf auf.",
        "errors": exc.errors,
    }


def design_materials(catalog: Catalog) -> dict[str, Any]:
    """Materials usable in free-form designs, in a compact form for the LLM."""
    items: list[dict[str, Any]] = []
    for item in catalog.items:
        if not item.designable:
            continue
        entry: dict[str, Any] = {"id": item.id, "name": item.name, "kind": item.kind}
        if item.kind == "linear" and item.section_mm:
            entry["section_mm"] = list(item.section_mm)
            entry["max_length_mm"] = max(item.stock_lengths_mm)
            entry["eur_per_m"] = f"{item.price_min}–{item.price_max}"
        elif item.kind == "sheet" and item.sheet_mm:
            entry["thickness_mm"] = item.thickness_mm
            entry["sheet_mm"] = list(item.sheet_mm)
            entry["eur_per_sheet"] = f"{item.price_min}–{item.price_max}"
        elif item.size_mm:
            entry["fixed_size_mm"] = list(item.size_mm)
            entry["placeable"] = True
        else:
            entry["use"] = "finish" if item.kind == "finish" else "hardware"
        if item.hardware_type:
            entry["hardware_type"] = item.hardware_type
        entry["outdoor"] = item.outdoor
        items.append(entry)
    rules = catalog.lumber
    lumber = {
        "id_format": "lumber_<species>_<thickness>x<width>",
        "example": "lumber_douglas_18x96",
        "explanation": (
            "Made-to-order lumber: every species below is available in ANY cross-section "
            "(boards, battens, beams). Use it whenever the catalog items above do not have the "
            "species or section the user wants. Price is derived from the wood volume."
        ),
        "thickness_mm": [rules.min_thickness_mm, rules.max_thickness_mm],
        "max_width_mm": rules.max_width_mm,
        "species": [
            {
                "species": key,
                "label": m.label,
                "eur_per_m3": f"{m.lumber_price_m3[0]}–{m.lumber_price_m3[1]}",
                "max_length_mm": max(m.lumber_stock_lengths_mm or [3000]),
                "outdoor": m.outdoor,
            }
            for key, m in catalog.lumber_species().items()
            if m.lumber_price_m3
        ],
    }
    return {"catalog_items": items, "lumber": lumber}


def _design_json(design: AssemblyDesign) -> dict[str, Any]:
    return design.model_dump(mode="json", exclude_defaults=True)


def planning_overview(engine: Engine) -> str:
    """Packs and templates as compact text for the instructions (saves a tool round trip)."""
    lines = ["Planbar ohne freien Entwurf (Parameter in Klammern, Längen in mm):"]
    for pack in engine.describe_packs():
        props = pack.params_schema.get("properties", {})
        lines.append(
            f"- Pack {pack.id} – {pack.title}: {pack.description} ({', '.join(props)}) "
            "→ create_project"
        )
    for tpl in templates().values():
        params = ", ".join(
            f"{p.name}={'|'.join(str(o.value) for o in p.options)}" if p.options else p.name
            for p in tpl.design.params
        )
        lines.append(
            f"- Vorlage {tpl.key} – {tpl.title}: {tpl.description} ({params}) "
            "→ create_from_template"
        )
    return "\n".join(lines)


async def _store_explanation(
    ctx: RunContext[AgentDeps], project_id: UUID, text: str | None
) -> None:
    """Store the AI explanation passed along with a create/redesign call (caller holds the lock)."""
    if not text or not text.strip():
        return
    await ctx.deps.projects.execute(
        ctx.deps.owner_id,
        project_id,
        AddNote(text=text.strip()[:2000], origin=Origin.AI),
        actor="agent",
        trace_id=ctx.deps.trace_id,
    )


def _target(ctx: RunContext[AgentDeps], new_project: bool) -> UUID | None:
    """Project that a create call re-plans as its next version (None = create a new project)."""
    return None if new_project else ctx.deps.project_id


def _action(target: UUID | None) -> str:
    return "created" if target is None else "replanned"


def _attempt(
    ctx: RunContext[AgentDeps], tool: str, design: AssemblyDesign, errors: list[str]
) -> None:
    ctx.deps.design_attempts.append(
        {
            "tool": tool,
            "accepted": not errors,
            "errors": errors,
            "design": design.model_dump(mode="json"),
        }
    )


def build_agent(model: Model, engine: Engine) -> Agent[AgentDeps, str]:
    agent: Agent[AgentDeps, str] = Agent(
        model,
        deps_type=AgentDeps,
        instructions=[INSTRUCTIONS, planning_overview(engine)],
        retries=2,
    )

    @agent.tool
    def list_construction_packs(ctx: RunContext[AgentDeps]) -> dict[str, Any]:
        """List what can be planned: verified packs (with parameter schema) and design templates.

        Anything else can be designed freely with design_project.
        """
        return {
            "packs": [d.model_dump() for d in ctx.deps.projects.engine.describe_packs()],
            "templates": [
                {
                    "key": t.key,
                    "title": t.title,
                    "description": t.description,
                    "params": {p.name: p.label for p in t.design.params},
                }
                for t in templates().values()
            ],
        }

    @agent.tool
    def list_materials(ctx: RunContext[AgentDeps]) -> dict[str, Any]:
        """Materials for free-form designs: catalog items (profiles, sheets, placeable pieces,
        hardware, finishes) and made-to-order lumber in any species and cross-section."""
        return design_materials(ctx.deps.projects.engine.catalog)

    @agent.tool_plain
    def get_template_design(template_key: str) -> dict[str, Any]:
        """Return the full design of a template as an example or starting point for design_project."""
        try:
            return _design_json(template(template_key).design)
        except KeyError:
            return _error(f"Unbekannte Vorlage '{template_key}'")

    @agent.tool
    async def create_from_template(
        ctx: RunContext[AgentDeps],
        template_key: str,
        title: str,
        params: ParamsArg,
        explanation: str | None = None,
        untreated: bool = False,
        new_project: bool = False,
    ) -> dict[str, Any]:
        """Create a project from a design template; omitted parameters use template defaults.

        Args:
            template_key: Template key, e.g. "shelf".
            title: Short German project title.
            params: Template parameters (lengths in mm).
            explanation: Optional short German explanation of the construction (labelled as AI).
            untreated: True when the user wants no surface treatment (no oil or glaze).
            new_project: Only true if the user explicitly wants another, separate project. Otherwise
                an active project gets this as its next version (history and chat stay).
        """
        target = _target(ctx, new_project)
        # Models tend to put the flag and design-level fields among the template parameters.
        params = dict(params)
        untreated = bool(params.pop("untreated", untreated))
        for key in ("use", "support"):
            params.pop(key, None)
        async with ctx.deps.write_lock:
            try:
                outcome = await ctx.deps.projects.create_from_template(
                    ctx.deps.owner_id,
                    template_key=template_key,
                    title=title,
                    params=params,
                    untreated=untreated,
                    replace_project_id=target,
                    actor="agent",
                    trace_id=ctx.deps.trace_id,
                )
            except ParameterError as exc:
                return _error("Ungültige Parameter: " + "; ".join(exc.errors))
            except UnknownPackError:
                return _error(f"Unbekannte Vorlage '{template_key}'")
            await _store_explanation(ctx, outcome.project.id, explanation)
        ctx.deps.project_id = outcome.project.id
        ctx.deps.changed_projects.add(outcome.project.id)
        return {"action": _action(target), "project": project_summary(outcome.project)}

    @agent.tool(retries=3)
    async def design_project(
        ctx: RunContext[AgentDeps],
        title: str,
        design: DesignArg,
        params: ParamsArg | None = None,
        explanation: str | None = None,
        new_project: bool = False,
    ) -> dict[str, Any]:
        """Create a project from a free-form parametric design (when no pack or template fits).

        The engine validates the design (catalog dimensions, collisions, connectivity, floor
        contact) and derives BOM, cut list, screws, costs and drawings. On rejection fix the
        listed errors and call again with the complete corrected design.

        Args:
            title: Short German project title.
            design: The complete design. Coordinates in mm: x = width (right), y = depth (back),
                z = height (up), floor z = 0; ``at`` is the part's minimum corner.
            params: Optional initial parameter values (otherwise the design defaults).
            explanation: Short German explanation of why the construction looks like this
                (material, cross-sections, joints); stored only if the engine accepts the design.
            new_project: Only true if the user explicitly wants another, separate project. Otherwise
                an active project gets this as its next version (history and chat stay).
        """
        design = design.model_copy(update={"origin": Origin.AI})
        target = _target(ctx, new_project)
        async with ctx.deps.write_lock:
            try:
                if target is not None:
                    outcome = await ctx.deps.projects.replan(
                        ctx.deps.owner_id,
                        target,
                        pack_id=DESIGN_PACK_ID,
                        title=title,
                        params=params or {},
                        design=design,
                        actor="agent",
                        trace_id=ctx.deps.trace_id,
                    )
                else:
                    outcome = await ctx.deps.projects.create(
                        ctx.deps.owner_id,
                        pack_id=DESIGN_PACK_ID,
                        title=title,
                        params=params or {},
                        design=design,
                        actor="agent",
                        trace_id=ctx.deps.trace_id,
                    )
            except DesignRejectedError as exc:
                _attempt(ctx, "design_project", design, exc.errors)
                return _design_rejected(exc)
            except ParameterError as exc:
                return _error("Ungültige Parameter: " + "; ".join(exc.errors))
            _attempt(ctx, "design_project", design, [])
            await _store_explanation(ctx, outcome.project.id, explanation)
        ctx.deps.project_id = outcome.project.id
        ctx.deps.changed_projects.add(outcome.project.id)
        return {"action": _action(target), "project": project_summary(outcome.project)}

    @agent.tool
    async def get_current_design(ctx: RunContext[AgentDeps]) -> dict[str, Any]:
        """Return the design of the current free-form project (to modify it with redesign_project)."""
        if ctx.deps.project_id is None:
            return _error("Es ist kein Projekt aktiv.")
        try:
            model = await ctx.deps.projects.get(ctx.deps.owner_id, ctx.deps.project_id)
        except ProjectNotFoundError:
            return _error("Projekt nicht gefunden.")
        if model.inputs.design is None:
            return _error("Das Projekt nutzt ein Construction Pack; ändere es mit change_project.")
        return {"params": model.inputs.params, "design": _design_json(model.inputs.design)}

    @agent.tool(retries=3)
    async def redesign_project(
        ctx: RunContext[AgentDeps], design: DesignArg, explanation: str | None = None
    ) -> dict[str, Any]:
        """Replace the design of the current free-form project (structural changes such as an
        extra drawer or a different construction). Pure dimension changes use change_project.

        The previous AI explanation is removed and replaced by ``explanation`` if given."""
        design = design.model_copy(update={"origin": Origin.AI})
        async with ctx.deps.write_lock:
            if ctx.deps.project_id is None:
                return _error("Es ist kein Projekt aktiv.")
            try:
                outcome = await ctx.deps.projects.execute(
                    ctx.deps.owner_id,
                    ctx.deps.project_id,
                    ReplaceDesign(design=design),
                    actor="agent",
                    trace_id=ctx.deps.trace_id,
                )
            except DesignRejectedError as exc:
                _attempt(ctx, "redesign_project", design, exc.errors)
                return _design_rejected(exc)
            except ParameterError as exc:
                return _error("Ungültige Parameter: " + "; ".join(exc.errors))
            except (CommandError, ProjectNotFoundError) as exc:
                return _error(f"Änderung nicht möglich: {exc}")
            _attempt(ctx, "redesign_project", design, [])
            await _store_explanation(ctx, outcome.project.id, explanation)
        ctx.deps.changed_projects.add(outcome.project.id)
        return {
            "action": "changed",
            "project": project_summary(outcome.project),
            "diff": diff_summary(outcome.diff),
        }

    @agent.tool
    async def create_project(
        ctx: RunContext[AgentDeps],
        pack_id: str,
        title: str,
        params: ParamsArg,
        explanation: str | None = None,
        new_project: bool = False,
    ) -> dict[str, Any]:
        """Create a new project from a construction pack. Lengths in millimetres.

        Args:
            pack_id: Id of the construction pack, e.g. "raised_bed".
            title: Short project title in German, e.g. "Hochbeet am Gartenhaus".
            params: Pack parameters; omitted parameters use the pack defaults.
            explanation: Optional short German explanation of the construction (labelled as AI).
            new_project: Only true if the user explicitly wants another, separate project. Otherwise
                an active project gets this as its next version (history and chat stay).
        """
        target = _target(ctx, new_project)
        async with ctx.deps.write_lock:
            try:
                if target is not None:
                    outcome = await ctx.deps.projects.replan(
                        ctx.deps.owner_id,
                        target,
                        pack_id=pack_id,
                        title=title,
                        params=params,
                        actor="agent",
                        trace_id=ctx.deps.trace_id,
                    )
                else:
                    outcome = await ctx.deps.projects.create(
                        ctx.deps.owner_id,
                        pack_id=pack_id,
                        title=title,
                        params=params,
                        actor="agent",
                        trace_id=ctx.deps.trace_id,
                    )
            except ParameterError as exc:
                return _error("Ungültige Parameter: " + "; ".join(exc.errors))
            except UnknownPackError:
                return _error(f"Unbekanntes Construction Pack '{pack_id}'")
            await _store_explanation(ctx, outcome.project.id, explanation)
        ctx.deps.project_id = outcome.project.id
        ctx.deps.changed_projects.add(outcome.project.id)
        return {"action": _action(target), "project": project_summary(outcome.project)}

    @agent.tool
    async def change_project(ctx: RunContext[AgentDeps], command: AgentCommand) -> dict[str, Any]:
        """Change the current project with a typed command (lengths in millimetres)."""
        async with ctx.deps.write_lock:
            if ctx.deps.project_id is None:
                return _error("Es ist noch kein Projekt aktiv. Erstelle zuerst ein Projekt.")
            try:
                outcome = await ctx.deps.projects.execute(
                    ctx.deps.owner_id,
                    ctx.deps.project_id,
                    command,
                    actor="agent",
                    trace_id=ctx.deps.trace_id,
                )
            except ParameterError as exc:
                return _error("Ungültige Parameter: " + "; ".join(exc.errors))
            except (CommandError, ProjectNotFoundError) as exc:
                return _error(f"Änderung nicht möglich: {exc}")
        ctx.deps.changed_projects.add(outcome.project.id)
        return {
            "action": "changed",
            "project": project_summary(outcome.project),
            "diff": diff_summary(outcome.diff),
        }

    @agent.tool
    async def undo_last_change(ctx: RunContext[AgentDeps]) -> dict[str, Any]:
        """Undo the last change of the current project."""
        async with ctx.deps.write_lock:
            if ctx.deps.project_id is None:
                return _error("Es ist kein Projekt aktiv.")
            try:
                outcome = await ctx.deps.projects.undo(
                    ctx.deps.owner_id,
                    ctx.deps.project_id,
                    actor="agent",
                    trace_id=ctx.deps.trace_id,
                )
            except (CommandError, ProjectNotFoundError) as exc:
                return _error(f"Rückgängig nicht möglich: {exc}")
        ctx.deps.changed_projects.add(outcome.project.id)
        return {
            "action": "undone",
            "project": project_summary(outcome.project),
            "diff": diff_summary(outcome.diff),
        }

    @agent.tool
    async def get_project(ctx: RunContext[AgentDeps]) -> dict[str, Any]:
        """Return the current project's key figures, costs, variants and notices."""
        if ctx.deps.project_id is None:
            return _error("Es ist kein Projekt aktiv.")
        try:
            model = await ctx.deps.projects.get(ctx.deps.owner_id, ctx.deps.project_id)
        except ProjectNotFoundError:
            return _error("Projekt nicht gefunden.")
        return {"project": project_summary(model)}

    @agent.tool
    async def add_explanation(ctx: RunContext[AgentDeps], text: str) -> dict[str, Any]:
        """Store a short explanation of the design for the project document (labelled as AI)."""
        async with ctx.deps.write_lock:
            if ctx.deps.project_id is None:
                return _error("Es ist kein Projekt aktiv.")
            try:
                await ctx.deps.projects.execute(
                    ctx.deps.owner_id,
                    ctx.deps.project_id,
                    AddNote(text=text[:2000], origin=Origin.AI),
                    actor="agent",
                    trace_id=ctx.deps.trace_id,
                )
            except (CommandError, ProjectNotFoundError) as exc:
                return _error(f"Notiz nicht gespeichert: {exc}")
        return {"action": "note_added"}

    return agent
