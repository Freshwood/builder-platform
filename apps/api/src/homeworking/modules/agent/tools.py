"""Agent definition and tools. Tools translate LLM intents into typed project commands."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Annotated, Any, Protocol
from uuid import UUID

from pydantic import Field, ValidationError
from pydantic_ai import Agent, AgentRunResult, ModelRetry, RunContext
from pydantic_ai.capabilities import AbstractCapability, ProcessHistory, WrapModelRequestHandler
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models import Model, ModelRequestContext
from pydantic_ai.tools import ToolDefinition

from calc_engine.catalog import Catalog
from calc_engine.engine import DesignRejectedError
from calc_engine.pipeline.gaps import is_ready
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
from construction_model.pipeline import Spec
from homeworking.modules.agent.args import JsonTolerant, RepairToolArgs
from homeworking.modules.agent.history import process_history
from homeworking.modules.agent.prompts import INSTRUCTIONS
from homeworking.modules.agent.request_shape import error_info, request_shape
from homeworking.modules.projects.service import (
    CommandOutcome,
    ProjectNotFoundError,
    ProjectService,
)

# Pipeline runs one chat turn may start (a failed plan is explained to the user after that).
MAX_PLAN_RUNS = 2

# Upper bound of AddNote.text; explanations span several paragraphs.
NOTE_MAX_CHARS = 4000


AgentCommand = Annotated[
    SetParameters | ChangeParameterBy | SelectVariant | Rename | SetRegion | SetPrice,
    Field(discriminator="type"),
    JsonTolerant,
]
DesignArg = Annotated[AssemblyDesign, JsonTolerant]
SpecArg = Annotated[Spec, JsonTolerant]
ParamsArg = Annotated[dict[str, ParamValue], JsonTolerant]


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
    """Plans a new design in stages (ADR-0010). Implemented in the API layer, which owns the
    pipeline, so that the agent does not depend on it."""

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
    # Whether ``save_design`` may create a project. Off with a real model: a live run showed it
    # falling back to the old one-call design loop (7 attempts, 134K tokens) when the pipeline
    # failed. The offline model drafts its canned designs with it, so tests keep it on.
    save_design_creates: bool = True
    # The model may call several tools in parallel; project writes must run one after another,
    # otherwise they race for the next command sequence number.
    write_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _eur(value: Any) -> str:
    return f"{value:.0f} €"


def project_summary(model: ProjectModel, *, with_bom: bool = False) -> dict[str, Any]:
    """Compact, token-friendly view of a project for the LLM.

    The bill of materials (about half of the summary) is only included on request
    (get_project); every create/change result would otherwise repeat it in the history.
    """
    r = model.result
    summary: dict[str, Any] = {
        "project_id": str(model.id),
        "title": model.inputs.title,
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
    if with_bom:
        summary["bom"] = [
            {
                "item_id": line.item_id,
                "name": f"{line.name} ({line.spec})",
                "quantity": f"{line.quantity:f} {line.unit}",
                "unit_price_eur": f"{line.unit_price.min}–{line.unit_price.max}",
                "source": line.price_source,
            }
            for line in r.bom
        ]
    return summary


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


def _design_rejected(exc: DesignRejectedError) -> dict[str, Any]:
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


def materials_table(catalog: Catalog) -> str:
    """The design materials as a compact text table (about a third of the JSON tokens)."""
    data = design_materials(catalog)
    lines = ["Katalog: id | Name | Maße mm | Preis € | außen | Beschlagtyp"]
    for e in data["catalog_items"]:
        if "section_mm" in e:
            size = f"{e['section_mm'][0]}x{e['section_mm'][1]} ≤{e['max_length_mm']}"
            price = f"{e['eur_per_m']}/m"
        elif "sheet_mm" in e:
            size = f"{e['thickness_mm']} Platte {e['sheet_mm'][0]}x{e['sheet_mm'][1]}"
            price = f"{e['eur_per_sheet']}/Platte"
        elif "fixed_size_mm" in e:
            size = "fest " + "x".join(str(v) for v in e["fixed_size_mm"])
            price = ""
        else:
            size, price = e["use"], ""
        outdoor = "ja" if e["outdoor"] else "nein"
        lines.append(
            f"{e['id']} | {e['name']} | {size} | {price} | {outdoor} | {e.get('hardware_type', '')}"
        )
    lumber = data["lumber"]
    lines += [
        "",
        f"Maßholz {lumber['id_format']} (z. B. {lumber['example']}): jede Holzart in JEDEM "
        f"Querschnitt, Stärke {lumber['thickness_mm'][0]}–{lumber['thickness_mm'][1]} mm, "
        f"Breite ≤{lumber['max_width_mm']} mm; nehmen, wenn kein Katalogartikel passt.",
        "species | Name | €/m³ | max Länge mm | außen",
        *(
            f"{sp['species']} | {sp['label']} | {sp['eur_per_m3']} | {sp['max_length_mm']} | "
            f"{'ja' if sp['outdoor'] else 'nein'}"
            for sp in lumber["species"]
        ),
    ]
    return "\n".join(lines)


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


# Upper bound of the raw tool arguments kept per attempt (a full design is about 20-50 kB).
RAW_ARGS_MAX_CHARS = 200_000


def stored_raw_args(args: str | dict[str, Any] | None) -> str | dict[str, Any] | None:
    """Raw tool arguments as the model sent them, JSON-safe and bounded in size."""
    if args is None:
        return None
    text = args if isinstance(args, str) else json.dumps(args, ensure_ascii=False, default=str)
    if len(text) > RAW_ARGS_MAX_CHARS:
        return f"{text[:RAW_ARGS_MAX_CHARS]}…[truncated, {len(text)} chars in total]"
    return args if isinstance(args, str) else json.loads(text)


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
    ``no_project`` or ``exception`` (older runs may also have ``unknown_pack``). ``tool``, ``accepted``, ``errors`` and
    ``design`` (null unless a design was validated) are the keys older runs already have.
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


def _attempt(
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


def _command_outcome(exc: Exception) -> str:
    return "not_found" if isinstance(exc, ProjectNotFoundError) else "command_error"


def _fail(
    ctx: RunContext[AgentDeps],
    outcome: str,
    message: str,
    errors: list[str] | None = None,
    design: AssemblyDesign | None = None,
) -> dict[str, Any]:
    """Record a failed tool call and return the error message to the model."""
    _attempt(ctx, outcome, errors if errors is not None else [message], design)
    return _error(message)


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


@dataclass
class RecordUsage(AbstractCapability[AgentDeps]):
    """Store tokens and the provider's resolved model name of every model response."""

    async def after_model_request(
        self,
        ctx: RunContext[AgentDeps],
        *,
        request_context: ModelRequestContext,
        response: ModelResponse,
    ) -> ModelResponse:
        usage = response.usage
        ctx.deps.requests.append(
            {
                "model": response.model_name,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_read_tokens": usage.cache_read_tokens,
            }
        )
        return response

    @classmethod
    def get_serialization_name(cls) -> str | None:
        return None


@dataclass
class RecordRequestShape(AbstractCapability[AgentDeps]):
    """Keep the structure of every model request as sent, and of the error if the call fails.

    ``wrap_model_request`` sees the final messages (after history processing and the framework's
    clean-up), i.e. what the model class maps to the provider array. Observing only: the request
    is passed on unchanged, and a failure while recording never breaks the run.
    """

    async def wrap_model_request(
        self,
        ctx: RunContext[AgentDeps],
        *,
        request_context: ModelRequestContext,
        handler: WrapModelRequestHandler,
    ) -> ModelResponse:
        deps = ctx.deps
        deps.request_count += 1
        number = deps.request_count
        try:
            deps.last_request_shape = await request_shape(request_context, number)
        except Exception:  # pragma: no cover - diagnostics must never break a run
            deps.last_request_shape = None
        deps.request_open = number
        try:
            response = await handler(request_context)
        except Exception as error:
            self._remember(deps, number, error)
            raise
        deps.request_open = None
        return response

    async def on_model_request_error(
        self,
        ctx: RunContext[AgentDeps],
        *,
        request_context: ModelRequestContext,
        error: Exception,
    ) -> ModelResponse:
        self._remember(ctx.deps, ctx.deps.request_count, error)
        raise error

    async def on_run_error(
        self, ctx: RunContext[AgentDeps], *, error: BaseException
    ) -> AgentRunResult[Any]:
        """A streamed request opens lazily: its provider error surfaces here, not in the hooks above.

        (``wrap_run_event_stream`` would see it too, but defining it makes ``agent.run`` stream.)
        Only a run that died while a request was in flight counts as a failed model call.
        """
        deps = ctx.deps
        known = (deps.last_request_error or {}).get("request_number")
        if deps.request_open is not None and known != deps.request_open:
            self._remember(deps, deps.request_open, error)
        raise error

    @staticmethod
    def _remember(deps: AgentDeps, number: int, error: BaseException) -> None:
        # ModelRetry is a retry request of the framework, not a failure of the call.
        if isinstance(error, ModelRetry):
            return
        deps.last_request_error = {"request_number": number, **error_info(error)}

    @classmethod
    def get_serialization_name(cls) -> str | None:
        return None


def _validation_messages(error: ValidationError | ModelRetry) -> list[str]:
    """Compact texts of an argument error (location, message, type); no input echo."""
    if isinstance(error, ModelRetry):
        return [str(error.message)]
    return [
        f"{'.'.join(str(part) for part in e['loc'])}: {e['msg']} [{e['type']}]"
        for e in error.errors(include_url=False, include_input=False, include_context=False)
    ]


@dataclass
class RecordToolAttempts(AbstractCapability[AgentDeps]):
    """Keep the raw arguments of every tool call and record calls that fail validation.

    Failures inside a tool body are recorded there (``_attempt``, ``_fail``); this capability
    covers what never reaches the body: schema violations (e.g. an extra key inside ``design``),
    JSON that cannot be repaired (``RepairToolArgs``) and unexpected exceptions.
    """

    async def before_tool_validate(
        self,
        ctx: RunContext[AgentDeps],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: str | dict[str, Any],
    ) -> str | dict[str, Any]:
        ctx.deps.raw_tool_args[call.tool_call_id] = args
        return args

    async def on_tool_validate_error(
        self,
        ctx: RunContext[AgentDeps],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: str | dict[str, Any],
        error: ValidationError | ModelRetry,
    ) -> dict[str, Any]:
        ctx.deps.design_attempts.append(
            tool_attempt(
                tool=call.tool_name,
                tool_call_id=call.tool_call_id,
                outcome="invalid_args",
                errors=_validation_messages(error),
                raw_args=args,
            )
        )
        raise error

    async def on_tool_execute_error(
        self,
        ctx: RunContext[AgentDeps],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: dict[str, Any],
        error: Exception,
    ) -> Any:
        ctx.deps.design_attempts.append(
            tool_attempt(
                tool=call.tool_name,
                tool_call_id=call.tool_call_id,
                outcome="exception",
                errors=[f"{type(error).__name__}: {error}"[:2000]],
                raw_args=ctx.deps.raw_tool_args.get(call.tool_call_id),
            )
        )
        raise error

    @classmethod
    def get_serialization_name(cls) -> str | None:
        return None


def build_agent(model: Model) -> Agent[AgentDeps, str]:
    agent: Agent[AgentDeps, str] = Agent(
        model,
        deps_type=AgentDeps,
        instructions=INSTRUCTIONS,
        retries=2,
        capabilities=[
            ProcessHistory(process_history),
            RepairToolArgs(),
            RecordToolAttempts(),
            RecordUsage(),
            RecordRequestShape(),
        ],
    )

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
            return _fail(ctx, "no_planner", "Entwürfe sind derzeit nicht verfügbar.")
        if not is_ready(spec):
            return _fail(
                ctx, "missing_size", "Für den Entwurf fehlen Maße (width_mm, depth_mm, height_mm)."
            )
        if ctx.deps.plan_runs >= MAX_PLAN_RUNS:
            return _fail(
                ctx,
                "plan_limit",
                "Der Entwurf ist mehrfach nicht gelungen. Erkläre dem Nutzer kurz, woran es "
                "lag, und frage, was du an den Angaben ändern sollst.",
            )
        ctx.deps.plan_runs += 1
        try:
            planned = await ctx.deps.planner.plan(spec)
        except PlanFailedError as exc:
            _attempt(ctx, "engine_rejected", exc.errors)
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
                _attempt(ctx, "engine_rejected", exc.errors, design)
                return _design_rejected(exc)
            except (CommandError, ProjectNotFoundError) as exc:
                return _fail(
                    ctx, _command_outcome(exc), f"Änderung nicht möglich: {exc}", design=design
                )
            _attempt(ctx, "accepted", [], design)
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
            return _fail(
                ctx,
                "use_plan_design",
                "Neue Projekte planst du mit plan_design; save_design ist nur zum Umbauen.",
            )
        async with ctx.deps.write_lock:
            try:
                outcome = await _save_design(ctx, target, design, title, params)
            except DesignRejectedError as exc:
                _attempt(ctx, "engine_rejected", exc.errors, design)
                return _design_rejected(exc)
            except (CommandError, ProjectNotFoundError) as exc:
                return _fail(
                    ctx, _command_outcome(exc), f"Änderung nicht möglich: {exc}", design=design
                )
            _attempt(ctx, "accepted", [], design)
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
            return _fail(ctx, "no_project", "Es ist kein Projekt aktiv.")
        try:
            model = await ctx.deps.projects.get(ctx.deps.owner_id, ctx.deps.project_id)
        except ProjectNotFoundError:
            return _fail(ctx, "not_found", "Projekt nicht gefunden.")
        return {"params": model.inputs.params, "design": _design_json(model.inputs.design)}

    @agent.tool
    async def change_project(ctx: RunContext[AgentDeps], command: AgentCommand) -> dict[str, Any]:
        """Change the current project with a typed command (lengths in millimetres)."""
        async with ctx.deps.write_lock:
            if ctx.deps.project_id is None:
                return _fail(
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
                return _fail(
                    ctx,
                    "parameter_error",
                    "Ungültige Parameter: " + "; ".join(exc.errors),
                    exc.errors,
                )
            except (CommandError, ProjectNotFoundError) as exc:
                return _fail(ctx, _command_outcome(exc), f"Änderung nicht möglich: {exc}")
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
                return _fail(ctx, "no_project", "Es ist kein Projekt aktiv.")
            try:
                outcome = await ctx.deps.projects.undo(
                    ctx.deps.owner_id,
                    ctx.deps.project_id,
                    actor="agent",
                    trace_id=ctx.deps.trace_id,
                )
            except (CommandError, ProjectNotFoundError) as exc:
                return _fail(ctx, _command_outcome(exc), f"Rückgängig nicht möglich: {exc}")
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
            return _fail(ctx, "no_project", "Es ist kein Projekt aktiv.")
        try:
            model = await ctx.deps.projects.get(ctx.deps.owner_id, ctx.deps.project_id)
        except ProjectNotFoundError:
            return _fail(ctx, "not_found", "Projekt nicht gefunden.")
        return {"project": project_summary(model, with_bom=True)}

    @agent.tool
    async def add_explanation(ctx: RunContext[AgentDeps], text: str) -> dict[str, Any]:
        """Store an additional explanation of the design for the project document (labelled as AI)."""
        async with ctx.deps.write_lock:
            if ctx.deps.project_id is None:
                return _fail(ctx, "no_project", "Es ist kein Projekt aktiv.")
            try:
                await ctx.deps.projects.execute(
                    ctx.deps.owner_id,
                    ctx.deps.project_id,
                    AddNote(text=text[:NOTE_MAX_CHARS], origin=Origin.AI),
                    actor="agent",
                    trace_id=ctx.deps.trace_id,
                )
            except (CommandError, ProjectNotFoundError) as exc:
                return _fail(ctx, _command_outcome(exc), f"Notiz nicht gespeichert: {exc}")
        return {"action": "note_added"}

    return agent
