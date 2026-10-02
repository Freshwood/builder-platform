"""Agent definition and tools. Tools translate LLM intents into typed project commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any
from uuid import UUID

from pydantic import Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model

from calc_engine.assembly.derive import DESIGN_PACK_ID
from calc_engine.assembly.templates import template, templates
from calc_engine.catalog import Catalog
from calc_engine.engine import DesignRejectedError, ParameterError, UnknownPackError
from construction_model.assembly import AssemblyDesign
from construction_model.commands import (
    AddNote,
    ChangeParameterBy,
    CommandError,
    Rename,
    ReplaceDesign,
    SelectVariant,
    SetParameters,
    SetRegion,
)
from construction_model.diff import ModelDiff
from construction_model.model import Origin, ParamValue, ProjectModel
from homeworking.modules.agent.prompts import INSTRUCTIONS
from homeworking.modules.projects.service import ProjectNotFoundError, ProjectService

AgentCommand = Annotated[
    SetParameters | ChangeParameterBy | SelectVariant | Rename | SetRegion,
    Field(discriminator="type"),
]


@dataclass
class AgentDeps:
    owner_id: UUID
    projects: ProjectService
    project_id: UUID | None
    trace_id: str
    changed_projects: set[UUID] = field(default_factory=set)


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


def design_materials(catalog: Catalog) -> list[dict[str, Any]]:
    """Catalog items usable in free-form designs, in a compact form for the LLM."""
    out: list[dict[str, Any]] = []
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
        entry["outdoor"] = item.outdoor
        out.append(entry)
    return out


def _design_json(design: AssemblyDesign) -> dict[str, Any]:
    return design.model_dump(mode="json", exclude_defaults=True)


def build_agent(model: Model) -> Agent[AgentDeps, str]:
    agent: Agent[AgentDeps, str] = Agent(
        model, deps_type=AgentDeps, instructions=INSTRUCTIONS, retries=2
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
    def list_materials(ctx: RunContext[AgentDeps]) -> list[dict[str, Any]]:
        """Catalog materials for free-form designs: profiles (linear), sheets, placeable pieces,
        hardware and finishes. Use exactly these ids and dimensions."""
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
        params: dict[str, ParamValue],
    ) -> dict[str, Any]:
        """Create a project from a design template; omitted parameters use template defaults.

        Args:
            template_key: Template key from list_construction_packs, e.g. "shelf".
            title: Short German project title.
            params: Template parameters (lengths in mm).
        """
        try:
            outcome = await ctx.deps.projects.create_from_template(
                ctx.deps.owner_id,
                template_key=template_key,
                title=title,
                params=params,
                actor="agent",
                trace_id=ctx.deps.trace_id,
            )
        except ParameterError as exc:
            return _error("Ungültige Parameter: " + "; ".join(exc.errors))
        except UnknownPackError:
            return _error(f"Unbekannte Vorlage '{template_key}'")
        ctx.deps.project_id = outcome.project.id
        ctx.deps.changed_projects.add(outcome.project.id)
        return {"action": "created", "project": project_summary(outcome.project)}

    @agent.tool(retries=3)
    async def design_project(
        ctx: RunContext[AgentDeps],
        title: str,
        design: AssemblyDesign,
        params: dict[str, ParamValue] | None = None,
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
        """
        design = design.model_copy(update={"origin": Origin.AI})
        try:
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
            return _design_rejected(exc)
        except ParameterError as exc:
            return _error("Ungültige Parameter: " + "; ".join(exc.errors))
        ctx.deps.project_id = outcome.project.id
        ctx.deps.changed_projects.add(outcome.project.id)
        return {"action": "created", "project": project_summary(outcome.project)}

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
        ctx: RunContext[AgentDeps], design: AssemblyDesign
    ) -> dict[str, Any]:
        """Replace the design of the current free-form project (structural changes such as an
        extra drawer or a different construction). Pure dimension changes use change_project."""
        if ctx.deps.project_id is None:
            return _error("Es ist kein Projekt aktiv.")
        design = design.model_copy(update={"origin": Origin.AI})
        try:
            outcome = await ctx.deps.projects.execute(
                ctx.deps.owner_id,
                ctx.deps.project_id,
                ReplaceDesign(design=design),
                actor="agent",
                trace_id=ctx.deps.trace_id,
            )
        except DesignRejectedError as exc:
            return _design_rejected(exc)
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
    async def create_project(
        ctx: RunContext[AgentDeps],
        pack_id: str,
        title: str,
        params: dict[str, ParamValue],
    ) -> dict[str, Any]:
        """Create a new project from a construction pack. Lengths in millimetres.

        Args:
            pack_id: Id of the construction pack, e.g. "raised_bed".
            title: Short project title in German, e.g. "Hochbeet am Gartenhaus".
            params: Pack parameters; omitted parameters use the pack defaults.
        """
        try:
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
        ctx.deps.project_id = outcome.project.id
        ctx.deps.changed_projects.add(outcome.project.id)
        return {"action": "created", "project": project_summary(outcome.project)}

    @agent.tool
    async def change_project(ctx: RunContext[AgentDeps], command: AgentCommand) -> dict[str, Any]:
        """Change the current project with a typed command (lengths in millimetres)."""
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
