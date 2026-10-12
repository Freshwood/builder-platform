"""Agent definition and tools. Tools translate LLM intents into typed project commands."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Annotated, Any
from uuid import UUID

from pydantic import Field, ValidationError
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.capabilities import AbstractCapability, ProcessHistory
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models import Model, ModelRequestContext
from pydantic_ai.tools import ToolDefinition

from calc_engine.assembly.derive import DESIGN_PACK_ID
from calc_engine.assembly.templates import template, templates
from calc_engine.catalog import Catalog
from calc_engine.engine import DesignRejectedError, Engine, ParameterError, UnknownPackError
from construction_model.assembly import SUPPORTS, USES, AssemblyDesign, Support, Use
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
from homeworking.modules.agent.args import JsonTolerant, RepairToolArgs
from homeworking.modules.agent.history import process_history
from homeworking.modules.agent.prompts import INSTRUCTIONS
from homeworking.modules.projects.service import (
    CommandOutcome,
    ProjectNotFoundError,
    ProjectService,
)

# Upper bound of AddNote.text; explanations span several paragraphs.
NOTE_MAX_CHARS = 4000


AgentCommand = Annotated[
    SetParameters | ChangeParameterBy | SelectVariant | Rename | SetRegion | SetPrice,
    Field(discriminator="type"),
    JsonTolerant,
]
DesignArg = Annotated[AssemblyDesign, JsonTolerant]
ParamsArg = Annotated[dict[str, ParamValue], JsonTolerant]


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


def _literal[T: str](value: Any, allowed: tuple[T, ...]) -> T | None:
    """``value`` if it is one of ``allowed`` (a design-level field found among the params)."""
    return next((a for a in allowed if a == value), None)


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
    ``unknown_pack``, ``no_project`` or ``exception``. ``tool``, ``accepted``, ``errors`` and
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
    """Create a design project, redesign the current one or re-plan it as a design project."""
    projects, owner, trace = ctx.deps.projects, ctx.deps.owner_id, ctx.deps.trace_id
    if target is None:
        return await projects.create(
            owner,
            pack_id=DESIGN_PACK_ID,
            title=title or design.object_type,
            params=params or {},
            design=design,
            actor="agent",
            trace_id=trace,
        )
    current = (await projects.get(owner, target)).inputs
    if current.design is not None and title is None and params is None:
        # Structural change of a free-form design: keeps valid params and user notes.
        return await projects.execute(
            owner, target, ReplaceDesign(design=design), actor="agent", trace_id=trace
        )
    return await projects.replan(
        owner,
        target,
        pack_id=DESIGN_PACK_ID,
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


def build_agent(model: Model, engine: Engine) -> Agent[AgentDeps, str]:
    agent: Agent[AgentDeps, str] = Agent(
        model,
        deps_type=AgentDeps,
        instructions=[INSTRUCTIONS, planning_overview(engine)],
        retries=2,
        capabilities=[
            ProcessHistory(process_history),
            RepairToolArgs(),
            RecordToolAttempts(),
            RecordUsage(),
        ],
    )

    @agent.tool
    def list_construction_packs(ctx: RunContext[AgentDeps]) -> dict[str, Any]:
        """List what can be planned: verified packs (with parameter schema) and design templates.

        Anything else can be designed freely with save_design.
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
    def list_materials(ctx: RunContext[AgentDeps]) -> str:
        """Materials for free-form designs: catalog items and made-to-order lumber."""
        return materials_table(ctx.deps.projects.engine.catalog)

    @agent.tool_plain
    def get_template_design(template_key: str) -> dict[str, Any]:
        """Return the full design of a template as an example or starting point for save_design."""
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
        use: Use | None = None,
        support: Support | None = None,
        new_project: bool = False,
    ) -> dict[str, Any]:
        """Create a project from a design template; omitted parameters use template defaults.

        Args:
            template_key: Template key, e.g. "shelf".
            title: Short German project title.
            params: Template parameters (lengths in mm).
            explanation: The "Warum so?" explanation (see instructions).
            untreated: True when the user wants no surface treatment (no oil or glaze).
            use: "outdoor" or "indoor" if the brief says so (otherwise the template's).
            support: "wall" for wall mounting, "floor" for standing (otherwise the template's).
            new_project: Only true if the user explicitly wants another, separate project.
        """
        target = _target(ctx, new_project)
        # Models tend to put the flag and design-level fields among the template parameters.
        params = dict(params)
        untreated = bool(params.pop("untreated", untreated))
        use = _literal(params.pop("use", None), USES) or use
        support = _literal(params.pop("support", None), SUPPORTS) or support
        async with ctx.deps.write_lock:
            try:
                outcome = await ctx.deps.projects.create_from_template(
                    ctx.deps.owner_id,
                    template_key=template_key,
                    title=title,
                    params=params,
                    untreated=untreated,
                    use=use,
                    support=support,
                    replace_project_id=target,
                    actor="agent",
                    trace_id=ctx.deps.trace_id,
                )
            except ParameterError as exc:
                return _fail(
                    ctx,
                    "parameter_error",
                    "Ungültige Parameter: " + "; ".join(exc.errors),
                    exc.errors,
                )
            except UnknownPackError:
                return _fail(ctx, "unknown_pack", f"Unbekannte Vorlage '{template_key}'")
            await _store_explanation(ctx, outcome.project.id, explanation)
        ctx.deps.project_id = outcome.project.id
        ctx.deps.changed_projects.add(outcome.project.id)
        return {"action": _action(target), "project": project_summary(outcome.project)}

    @agent.tool(retries=3)
    async def save_design(
        ctx: RunContext[AgentDeps],
        design: DesignArg,
        title: str | None = None,
        params: ParamsArg | None = None,
        explanation: str | None = None,
        new_project: bool = False,
    ) -> dict[str, Any]:
        """Save a free-form parametric design (when no pack or template fits) or replace the
        design of the current free-form project. The engine validates it and derives BOM, cut
        list, screws, costs and drawings; on rejection fix the listed errors and call again
        with the complete corrected design.

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
        async with ctx.deps.write_lock:
            try:
                outcome = await _save_design(ctx, target, design, title, params)
            except DesignRejectedError as exc:
                _attempt(ctx, "engine_rejected", exc.errors, design)
                return _design_rejected(exc)
            except ParameterError as exc:
                message = "Ungültige Parameter: " + "; ".join(exc.errors)
                return _fail(ctx, "parameter_error", message, exc.errors, design)
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
        """Return the design of the current free-form project (to change it with save_design)."""
        if ctx.deps.project_id is None:
            return _fail(ctx, "no_project", "Es ist kein Projekt aktiv.")
        try:
            model = await ctx.deps.projects.get(ctx.deps.owner_id, ctx.deps.project_id)
        except ProjectNotFoundError:
            return _fail(ctx, "not_found", "Projekt nicht gefunden.")
        if model.inputs.design is None:
            return _fail(
                ctx,
                "command_error",
                "Das Projekt nutzt ein Construction Pack; ändere es mit change_project.",
            )
        return {"params": model.inputs.params, "design": _design_json(model.inputs.design)}

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
            explanation: The "Warum so?" explanation (see instructions).
            new_project: Only true if the user explicitly wants another, separate project.
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
                return _fail(
                    ctx,
                    "parameter_error",
                    "Ungültige Parameter: " + "; ".join(exc.errors),
                    exc.errors,
                )
            except UnknownPackError:
                return _fail(ctx, "unknown_pack", f"Unbekanntes Construction Pack '{pack_id}'")
            await _store_explanation(ctx, outcome.project.id, explanation)
        ctx.deps.project_id = outcome.project.id
        ctx.deps.changed_projects.add(outcome.project.id)
        return {"action": _action(target), "project": project_summary(outcome.project)}

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
            except ParameterError as exc:
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
