"""The tools that create and change designs: planning, saving, reading the current design."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from pydantic_ai import Agent, RunContext

from homeworking.calc_engine.engine import DesignRejectedError
from homeworking.calc_engine.pipeline.gaps import is_ready
from homeworking.construction_model.assembly import AssemblyDesign
from homeworking.construction_model.commands import AddNote, CommandError, ReplaceDesign
from homeworking.construction_model.model import Origin, ParamValue
from homeworking.construction_model.pipeline import Spec
from homeworking.modules.agent.args import JsonTolerant
from homeworking.modules.agent.deps import (
    MAX_PLAN_RUNS,
    NOTE_MAX_CHARS,
    AgentDeps,
    PlanFailedError,
    command_outcome,
    fail,
    record_attempt,
)
from homeworking.modules.agent.summaries import diff_summary, materials_table, project_summary
from homeworking.modules.projects.service import CommandOutcome, ProjectNotFoundError

DesignArg = Annotated[AssemblyDesign, JsonTolerant]
SpecArg = Annotated[Spec, JsonTolerant]
ParamsArg = Annotated[dict[str, ParamValue], JsonTolerant]


def _design_rejected(exc: DesignRejectedError) -> dict[str, Any]:
    return {
        "error": "Der Entwurf wurde von der Engine abgelehnt. Korrigiere ihn und rufe das "
        "Werkzeug erneut mit dem vollständigen Entwurf auf.",
        "errors": exc.errors,
    }


def _design_json(design: AssemblyDesign) -> dict[str, Any]:
    return design.model_dump(mode="json", exclude_defaults=True)


async def _store_explanation(
    ctx: RunContext[AgentDeps], project_id: UUID, text: str | None
) -> None:
    """Store the AI explanation passed along with a create/redesign call (caller holds the lock)."""
    if not text or not text.strip():
        return
    await ctx.deps.projects.execute(
        ctx.deps.owner_id,
        project_id,
        AddNote(text=text.strip()[:NOTE_MAX_CHARS], origin=Origin.AI),
        actor="agent",
        trace_id=ctx.deps.trace_id,
    )


def _target(ctx: RunContext[AgentDeps], new_project: bool) -> UUID | None:
    """Project that a create call re-plans as its next version (None = create a new project)."""
    return None if new_project else ctx.deps.project_id


def _action(target: UUID | None) -> str:
    return "created" if target is None else "replanned"


async def _save_design(
    ctx: RunContext[AgentDeps],
    target: UUID | None,
    design: AssemblyDesign,
    title: str | None,
    params: dict[str, ParamValue] | None,
) -> CommandOutcome:
    """Create a project, redesign the current one or re-plan it with a new design."""
    projects, owner, trace = ctx.deps.projects, ctx.deps.owner_id, ctx.deps.trace_id
    if target is None:
        return await projects.create(
            owner,
            title=title or design.object_type,
            design=design,
            params=params or {},
            actor="agent",
            trace_id=trace,
        )
    if title is None and params is None:
        # Structural change of the design: keeps valid params and user notes.
        return await projects.execute(
            owner, target, ReplaceDesign(design=design), actor="agent", trace_id=trace
        )
    current = (await projects.get(owner, target)).inputs
    return await projects.replan(
        owner,
        target,
        title=title or current.title,
        params=params or {},
        design=design,
        actor="agent",
        trace_id=trace,
    )


def register_design_tools(agent: Agent[AgentDeps, str]) -> None:
    """Add the design tools to ``agent``. Names, docstrings and argument schemas are what the
    model sees (``prompt.lock``): change them only with a new PROMPT_VERSION."""

    @agent.tool
    def list_materials(ctx: RunContext[AgentDeps]) -> str:
        """Materials for free-form designs: catalog items and made-to-order lumber."""
        return materials_table(ctx.deps.projects.engine.catalog)

    @agent.tool(retries=1)
    async def plan_design(
        ctx: RunContext[AgentDeps], spec: SpecArg, title: str, new_project: bool = False
    ) -> dict[str, Any]:
        """Plan a new project or plan the current one anew. Stages design it, the engine checks
        it and writes the explanation and build steps; you only describe what is wanted.

        Args:
            spec: The brief with everything the customer said (lengths in mm).
            title: Short German project title.
            new_project: Only true if the user explicitly wants another, separate project.
        """
        if ctx.deps.planner is None:
            return fail(ctx, "no_planner", "Entwürfe sind derzeit nicht verfügbar.")
        if not is_ready(spec):
            return fail(ctx, "empty_brief", "Der Steckbrief enthält keine Beschreibung.")
        if ctx.deps.plan_runs >= MAX_PLAN_RUNS:
            return fail(
                ctx,
                "plan_limit",
                "Der Entwurf ist mehrfach nicht gelungen. Erkläre dem Nutzer kurz, woran es "
                "lag, und frage, was du an den Angaben ändern sollst.",
            )
        ctx.deps.plan_runs += 1
        try:
            planned = await ctx.deps.planner.plan(spec)
        except PlanFailedError as exc:
            record_attempt(ctx, "engine_rejected", exc.errors)
            return {
                "error": "Der Entwurf ist nicht gelungen. Sag dem Nutzer kurz, woran es lag, "
                "und biete an, es mit angepassten Angaben erneut zu versuchen.",
                "errors": exc.errors[:8],
            }
        design = planned.design.model_copy(update={"origin": Origin.AI})
        target = _target(ctx, new_project)
        async with ctx.deps.write_lock:
            try:
                outcome = await _save_design(ctx, target, design, title, None)
            except DesignRejectedError as exc:
                record_attempt(ctx, "engine_rejected", exc.errors, design)
                return _design_rejected(exc)
            except (CommandError, ProjectNotFoundError) as exc:
                return fail(
                    ctx, command_outcome(exc), f"Änderung nicht möglich: {exc}", design=design
                )
            record_attempt(ctx, "accepted", [], design)
            await _store_explanation(ctx, outcome.project.id, planned.explanation)
        ctx.deps.project_id = outcome.project.id
        ctx.deps.changed_projects.add(outcome.project.id)
        reply: dict[str, Any] = {
            "action": _action(target),
            "project": project_summary(outcome.project),
        }
        if target is not None:
            reply["diff"] = diff_summary(outcome.diff)
        return reply

    @agent.tool(retries=3)
    async def save_design(
        ctx: RunContext[AgentDeps],
        design: DesignArg,
        title: str | None = None,
        params: ParamsArg | None = None,
        explanation: str | None = None,
        new_project: bool = False,
    ) -> dict[str, Any]:
        """Save the one-off parametric design of a new project or replace the design of the
        current project. The engine validates it and derives BOM, cut list, screws, costs and
        drawings; on rejection fix the listed errors and call again with the complete corrected
        design.

        Args:
            design: The complete design.
            title: Short German project title (required for a new project).
            params: Optional parameter values (otherwise the design defaults).
            explanation: The "Warum so?" explanation (see instructions); stored only if the
                engine accepts the design.
            new_project: Only true if the user explicitly wants another, separate project.
        """
        design = design.model_copy(update={"origin": Origin.AI})
        target = _target(ctx, new_project)
        if target is None and not ctx.deps.save_design_creates:
            return fail(
                ctx,
                "use_plan_design",
                "Neue Projekte planst du mit plan_design; save_design ist nur zum Umbauen.",
            )
        async with ctx.deps.write_lock:
            try:
                outcome = await _save_design(ctx, target, design, title, params)
            except DesignRejectedError as exc:
                record_attempt(ctx, "engine_rejected", exc.errors, design)
                return _design_rejected(exc)
            except (CommandError, ProjectNotFoundError) as exc:
                return fail(
                    ctx, command_outcome(exc), f"Änderung nicht möglich: {exc}", design=design
                )
            record_attempt(ctx, "accepted", [], design)
            await _store_explanation(ctx, outcome.project.id, explanation)
        ctx.deps.project_id = outcome.project.id
        ctx.deps.changed_projects.add(outcome.project.id)
        reply: dict[str, Any] = {
            "action": _action(target),
            "project": project_summary(outcome.project),
        }
        if target is not None:
            reply["diff"] = diff_summary(outcome.diff)
        return reply

    @agent.tool
    async def get_current_design(ctx: RunContext[AgentDeps]) -> dict[str, Any]:
        """Return the design of the current project (to change it with save_design)."""
        if ctx.deps.project_id is None:
            return fail(ctx, "no_project", "Es ist kein Projekt aktiv.")
        try:
            model = await ctx.deps.projects.get(ctx.deps.owner_id, ctx.deps.project_id)
        except ProjectNotFoundError:
            return fail(ctx, "not_found", "Projekt nicht gefunden.")
        return {"params": model.inputs.params, "design": _design_json(model.inputs.design)}
