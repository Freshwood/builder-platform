"""The tools that change or read the open project: commands, undo, summary, explanation."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field
from pydantic_ai import Agent, RunContext

from homeworking.calc_engine.engine import DesignRejectedError
from homeworking.construction_model.commands import (
    AddNote,
    ChangeParameterBy,
    CommandError,
    Rename,
    SelectVariant,
    SetParameters,
    SetPrice,
    SetRegion,
)
from homeworking.construction_model.model import Origin
from homeworking.modules.agent.args import JsonTolerant
from homeworking.modules.agent.deps import NOTE_MAX_CHARS, AgentDeps, command_outcome, fail
from homeworking.modules.agent.summaries import diff_summary, project_summary
from homeworking.modules.projects.service import ProjectNotFoundError

AgentCommand = Annotated[
    SetParameters | ChangeParameterBy | SelectVariant | Rename | SetRegion | SetPrice,
    Field(discriminator="type"),
    JsonTolerant,
]


def register_project_tools(agent: Agent[AgentDeps, str]) -> None:
    """Add the project tools to ``agent``. Names, docstrings and argument schemas are what the
    model sees (``prompt.lock``): change them only with a new PROMPT_VERSION."""

    @agent.tool
    async def change_project(ctx: RunContext[AgentDeps], command: AgentCommand) -> dict[str, Any]:
        """Change the current project with a typed command (lengths in millimetres)."""
        async with ctx.deps.write_lock:
            if ctx.deps.project_id is None:
                return fail(
                    ctx,
                    "no_project",
                    "Es ist noch kein Projekt aktiv. Erstelle zuerst ein Projekt.",
                )
            try:
                outcome = await ctx.deps.projects.execute(
                    ctx.deps.owner_id,
                    ctx.deps.project_id,
                    command,
                    actor="agent",
                    trace_id=ctx.deps.trace_id,
                )
            except DesignRejectedError as exc:
                return fail(
                    ctx,
                    "parameter_error",
                    "Ungültige Parameter: " + "; ".join(exc.errors),
                    exc.errors,
                )
            except (CommandError, ProjectNotFoundError) as exc:
                return fail(ctx, command_outcome(exc), f"Änderung nicht möglich: {exc}")
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
                return fail(ctx, "no_project", "Es ist kein Projekt aktiv.")
            try:
                outcome = await ctx.deps.projects.undo(
                    ctx.deps.owner_id,
                    ctx.deps.project_id,
                    actor="agent",
                    trace_id=ctx.deps.trace_id,
                )
            except (CommandError, ProjectNotFoundError) as exc:
                return fail(ctx, command_outcome(exc), f"Rückgängig nicht möglich: {exc}")
        ctx.deps.changed_projects.add(outcome.project.id)
        return {
            "action": "undone",
            "project": project_summary(outcome.project),
            "diff": diff_summary(outcome.diff),
        }

    @agent.tool
    async def get_project(ctx: RunContext[AgentDeps]) -> dict[str, Any]:
        """Return the current project incl. bill of materials (item_id for set_price)."""
        if ctx.deps.project_id is None:
            return fail(ctx, "no_project", "Es ist kein Projekt aktiv.")
        try:
            model = await ctx.deps.projects.get(ctx.deps.owner_id, ctx.deps.project_id)
        except ProjectNotFoundError:
            return fail(ctx, "not_found", "Projekt nicht gefunden.")
        return {"project": project_summary(model, with_bom=True)}

    @agent.tool
    async def add_explanation(ctx: RunContext[AgentDeps], text: str) -> dict[str, Any]:
        """Store an additional explanation of the design for the project document (labelled as AI)."""
        async with ctx.deps.write_lock:
            if ctx.deps.project_id is None:
                return fail(ctx, "no_project", "Es ist kein Projekt aktiv.")
            try:
                await ctx.deps.projects.execute(
                    ctx.deps.owner_id,
                    ctx.deps.project_id,
                    AddNote(text=text[:NOTE_MAX_CHARS], origin=Origin.AI),
                    actor="agent",
                    trace_id=ctx.deps.trace_id,
                )
            except (CommandError, ProjectNotFoundError) as exc:
                return fail(ctx, command_outcome(exc), f"Notiz nicht gespeichert: {exc}")
        return {"action": "note_added"}
