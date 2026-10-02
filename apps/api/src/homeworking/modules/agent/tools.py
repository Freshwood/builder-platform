"""Agent definition and tools. Tools translate LLM intents into typed project commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any
from uuid import UUID

from pydantic import Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model

from calc_engine.engine import ParameterError, UnknownPackError
from construction_model.commands import (
    AddNote,
    ChangeParameterBy,
    CommandError,
    Rename,
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
        "summary": r.summary,
        "params": r.effective_params,
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


def build_agent(model: Model) -> Agent[AgentDeps, str]:
    agent: Agent[AgentDeps, str] = Agent(
        model, deps_type=AgentDeps, instructions=INSTRUCTIONS, retries=2
    )

    @agent.tool
    def list_construction_packs(ctx: RunContext[AgentDeps]) -> list[dict[str, Any]]:
        """List the construction packs that can be planned, with their parameter schema."""
        return [d.model_dump() for d in ctx.deps.projects.engine.describe_packs()]

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
