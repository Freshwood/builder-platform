"""State and shared helpers of the agent's tools: the per-turn dependencies, the planner port
and the records of failed or accepted tool calls."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from pydantic import TypeAdapter
from pydantic_ai import RunContext

from homeworking.construction_model.assembly import AssemblyDesign
from homeworking.construction_model.pipeline import Spec
from homeworking.modules.projects.service import ProjectNotFoundError, ProjectService

# Pipeline runs one chat turn may start (a failed plan is explained to the user after that).
MAX_PLAN_RUNS = 2

# Upper bound of AddNote.text; explanations span several paragraphs.
NOTE_MAX_CHARS = 4000


class PlanFailedError(Exception):
    """The staged pipeline could not deliver a design; ``errors`` are short German problems."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class PlannedDesign:
    design: AssemblyDesign
    explanation: str | None


class DesignPlanner(Protocol):
    """Plans a new design in stages (ADR-0010). Implemented by ``agent/planner.py``, which owns the
    pipeline run, so that the tools do not depend on the pipeline."""

    async def plan(self, spec: Spec) -> PlannedDesign: ...


@dataclass
class AgentDeps:
    owner_id: UUID
    projects: ProjectService
    project_id: UUID | None
    trace_id: str
    changed_projects: set[UUID] = field(default_factory=set)
    # Every design the model submitted, accepted or not, and every failed tool call of any tool
    # (invalid arguments, engine rejection, parameter and command errors); stored with the agent
    # run (it cost money) so that a failed run can become a regression test. Entry shape:
    # ``tool_attempt`` below. The name is historical (column ``agent_runs.design_attempts``).
    design_attempts: list[dict[str, Any]] = field(default_factory=list)
    # Raw arguments of the calls in flight, by tool_call_id (before repair and validation).
    raw_tool_args: dict[str, str | dict[str, Any] | None] = field(default_factory=dict)
    # Usage of every model request, also of runs that fail later (they cost money, too).
    requests: list[dict[str, Any]] = field(default_factory=list)
    # Shape (no text) of the latest model request as sent, and of the latest model call error;
    # overwritten per request (no growth), stored only if the run fails (``request_shape.py``).
    request_count: int = 0
    last_request_shape: dict[str, Any] | None = None
    last_request_error: dict[str, Any] | None = None
    # Number of the model request in flight, ``None`` once it returned (a streamed request fails
    # while its events are read, outside the model-request hooks).
    request_open: int | None = None
    # Plans new designs for ``plan_design``; without it the tool is unavailable.
    planner: DesignPlanner | None = None
    # Pipeline runs of this turn: every run costs a design's worth of tokens, so a failing
    # brief is not retried blindly (``MAX_PLAN_RUNS``).
    plan_runs: int = 0
    # Whether ``save_design`` may create a project (``Settings.save_design_creates``). Off with a
    # real model: a live run showed it falling back to the old one-call design loop (7 attempts,
    # 134K tokens) when the pipeline failed. The offline model drafts its canned designs with it.
    save_design_creates: bool = True
    # The model may call several tools in parallel; project writes must run one after another,
    # otherwise they race for the next command sequence number.
    write_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


# Upper bound of the raw tool arguments kept per attempt (a full design is about 20-50 kB).
RAW_ARGS_MAX_CHARS = 200_000
_RAW_ARGS_OBJECT: TypeAdapter[dict[str, Any]] = TypeAdapter(dict[str, Any])


def stored_raw_args(args: str | dict[str, Any] | None) -> str | dict[str, Any] | None:
    """Raw tool arguments as the model sent them, JSON-safe and bounded in size."""
    if args is None:
        return None
    text = args if isinstance(args, str) else json.dumps(args, ensure_ascii=False, default=str)
    if len(text) > RAW_ARGS_MAX_CHARS:
        return f"{text[:RAW_ARGS_MAX_CHARS]}…[truncated, {len(text)} chars in total]"
    # What a dict dumps to is a JSON object; the adapter keeps that typed and explicit.
    return args if isinstance(args, str) else _RAW_ARGS_OBJECT.validate_python(json.loads(text))


def tool_attempt(
    *,
    tool: str,
    tool_call_id: str | None,
    outcome: str,
    errors: list[str],
    raw_args: str | dict[str, Any] | None,
    design: AssemblyDesign | None = None,
) -> dict[str, Any]:
    """One entry of ``design_attempts`` (JSON column ``agent_runs.design_attempts``).

    ``outcome`` is ``accepted``, ``invalid_args`` (validation or JSON repair failed before the tool
    ran), ``engine_rejected``, ``parameter_error``, ``command_error``, ``not_found``,
    ``no_project`` or ``exception`` (older runs may also have ``unknown_pack``). ``tool``,
    ``accepted``, ``errors`` and ``design`` (null unless a design was validated) are the keys older
    runs already have.
    """
    return {
        "tool": tool,
        "tool_call_id": tool_call_id,
        "outcome": outcome,
        "accepted": outcome == "accepted",
        "errors": errors,
        "raw_args": stored_raw_args(raw_args),
        "design": design.model_dump(mode="json") if design is not None else None,
    }


def record_attempt(
    ctx: RunContext[AgentDeps],
    outcome: str,
    errors: list[str],
    design: AssemblyDesign | None = None,
) -> None:
    """Record the outcome of the tool call that runs now."""
    ctx.deps.design_attempts.append(
        tool_attempt(
            tool=ctx.tool_name or "",
            tool_call_id=ctx.tool_call_id,
            outcome=outcome,
            errors=errors,
            raw_args=ctx.deps.raw_tool_args.get(ctx.tool_call_id or ""),
            design=design,
        )
    )


def command_outcome(exc: Exception) -> str:
    return "not_found" if isinstance(exc, ProjectNotFoundError) else "command_error"


def fail(
    ctx: RunContext[AgentDeps],
    outcome: str,
    message: str,
    errors: list[str] | None = None,
    design: AssemblyDesign | None = None,
) -> dict[str, Any]:
    """Record a failed tool call and return the error message to the model."""
    record_attempt(ctx, outcome, errors if errors is not None else [message], design)
    return {"error": message}
