"""Stages 1 to 5 of the design pipeline (ADR-0010): intake, skeleton, modules and docs.

All stages call a model without tools and with a short prompt; the engine decides everything
that can be decided by rules (which questions are open, what the skeleton must satisfy, whether
the merged modules hold together). A stage returns its result together with the usage of every
model request, because AI results cost money and every run is stored (see ``api/pipeline.py``).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent, capture_run_messages
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelRequest, RetryPromptPart
from pydantic_ai.models import Model

from homeworking.calc_engine.engine import DesignRejectedError, Engine, default_engine
from homeworking.calc_engine.pipeline.gaps import apply_updates, is_ready, open_questions
from homeworking.calc_engine.pipeline.materials import digest
from homeworking.calc_engine.pipeline.merge import SKELETON, check, localize, merge, module_steps
from homeworking.calc_engine.pipeline.skeleton import (
    check_skeleton,
    default_params,
    module_box,
    normalize,
)
from homeworking.concurrency import run_blocking
from homeworking.construction_model.assembly import AssemblyDesign, DesignParam
from homeworking.construction_model.base import ParamValue
from homeworking.construction_model.pipeline import (
    Documentation,
    ModuleBrief,
    ModuleDesign,
    Question,
    Skeleton,
    Spec,
    SpecUpdates,
)
from homeworking.modules.llm.model import Models
from homeworking.modules.pipeline.prompts import DOCS, INTAKE, MODULES
from homeworking.modules.pipeline.prompts import SKELETON as SKELETON_PROMPT
from homeworking.settings import Settings

# Candidates handed to the intake model (what is still open); the customer sees at most 3.
MAX_OPEN_FOR_MODEL = 6
MAX_QUESTIONS = 3
SKELETON_ATTEMPTS = 2
# Repair rounds after the first module run; each re-runs only the modules the engine blames.
MODULE_REPAIRS = 2
MODULE_PARALLEL = 4
# Rounds in which the skeleton is revised because the merged modules fail on something no single
# module owns (parameters, overall shape). Every round runs all modules again.
SKELETON_REVISIONS = 1


class IntakeOutput(BaseModel):
    """What the intake model returns: facts read from the text and question wording."""

    model_config = ConfigDict(extra="forbid")

    updates: SpecUpdates = Field(default_factory=SpecUpdates)
    wording: dict[str, str] = Field(default_factory=dict, max_length=MAX_OPEN_FOR_MODEL)


@dataclass
class StageUsage:
    stage: str
    model: str = ""
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    duration_ms: int = 0

    def add(self, model: str, usage: Any) -> None:
        self.model = model
        self.requests += usage.requests
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.cache_read_tokens += usage.cache_read_tokens

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class StageFailedError(RuntimeError):
    """A model call of a stage failed (provider error, timeout, unusable output after the
    framework's retries). ``usage`` is what the stage had consumed up to then, so the run can still
    be stored (AI results cost money)."""

    def __init__(self, usage: StageUsage, cause: BaseException) -> None:
        reason = f"{type(cause).__name__}: {str(cause)[:300]}".rstrip(": ")
        super().__init__(f"Stage {usage.stage} failed: {reason}")
        self.usage = usage
        self.cause = cause


class SkeletonRejectedError(ValueError):
    """The model did not deliver a usable skeleton within its attempts."""

    def __init__(self, errors: list[str], usage: StageUsage) -> None:
        super().__init__("Skeleton rejected: " + "; ".join(errors))
        self.errors = errors
        self.usage = usage


@contextmanager
def _timed(usage: StageUsage) -> Iterator[None]:
    """Fill ``usage.duration_ms`` however the stage ends (result, rejection or failure)."""
    started = time.perf_counter()
    try:
        yield
    finally:
        usage.duration_ms = round((time.perf_counter() - started) * 1000)


@contextmanager
def _model_call(usage: StageUsage) -> Iterator[None]:
    """Turn whatever a model call raises into a :class:`StageFailedError` that carries the usage
    so far. Callers that tolerate unusable output catch ``UnexpectedModelBehavior`` inside."""
    try:
        yield
    except Exception as exc:
        raise StageFailedError(usage, exc) from exc


@dataclass
class IntakeResult:
    spec: Spec
    questions: list[Question]
    usage: StageUsage

    @property
    def ready(self) -> bool:
        return is_ready(self.spec)


@dataclass
class SkeletonResult:
    skeleton: Skeleton
    usage: StageUsage
    attempts: list[list[str]] = field(default_factory=list)  # engine problems per failed attempt
    messages: list[ModelMessage] = field(default_factory=list)  # the accepted run, for a repair


class ModulesRejectedError(ValueError):
    """The modules did not fit together within the repair rounds. ``errors`` maps a module id (or
    ``skeleton``) to the engine's problems."""

    def __init__(self, errors: dict[str, list[str]], usage: StageUsage) -> None:
        super().__init__(
            "Modules rejected: "
            + "; ".join(f"{key}: {' / '.join(texts)}" for key, texts in errors.items())
        )
        self.errors = errors
        self.usage = usage


@dataclass
class ModulesResult:
    design: AssemblyDesign
    modules: dict[str, ModuleDesign]
    usage: StageUsage
    repairs: list[dict[str, list[str]]] = field(default_factory=list)  # errors per repair round
    part_module: dict[str, str] = field(default_factory=dict)  # merged part id -> module id


@dataclass
class DocsResult:
    design: AssemblyDesign  # with the build steps
    explanation: str | None
    usage: StageUsage
    error: str | None = None  # the model call failed; the design carries the fallback step texts


@dataclass
class DesignResult:
    """A complete design from the staged pipeline."""

    design: AssemblyDesign
    explanation: str | None
    skeleton: Skeleton
    stages: list[StageUsage]


# Called after every stage of ``Pipeline.design`` with its usage and, if it failed, the error:
# every stage run is stored, also failed ones (AI results cost money).
StageRecorder = Callable[[StageUsage, str | None], Awaitable[None]]


def build_agents(
    intake: Model, skeleton: Model, modules: Model, docs: Model
) -> tuple[
    Agent[None, IntakeOutput],
    Agent[None, Skeleton],
    Agent[None, ModuleDesign],
    Agent[None, Documentation],
]:
    """The stage agents; also used by ``provenance`` to capture exactly what a request carries."""
    return (
        Agent(intake, output_type=IntakeOutput, instructions=INTAKE, retries=1),
        # Two output retries: the model sees its schema errors in the same short run, which is
        # cheaper than a new run (live run: one retry was often not enough).
        Agent(skeleton, output_type=Skeleton, instructions=SKELETON_PROMPT, retries=2),
        Agent(modules, output_type=ModuleDesign, instructions=MODULES, retries=2),
        Agent(docs, output_type=Documentation, instructions=DOCS, retries=1),
    )


def _real(models: Models | None) -> Models:
    if models is None:
        raise ValueError("Pipeline needs models unless LLM_MODE=test")
    return models


def _spec_line(spec: Spec) -> str:
    return "Steckbrief: " + spec.model_dump_json(exclude_none=True, exclude_defaults=True)


def _word(model_text: str | None, default: str) -> str:
    text = (model_text or "").strip()
    return text if 0 < len(text) <= 200 else default


def _why(messages: list[ModelMessage]) -> str:
    """The schema errors the model was last told about (empty if there were none)."""
    for message in reversed(messages):
        if isinstance(message, ModelRequest):
            for part in reversed(message.parts):
                if isinstance(part, RetryPromptPart):
                    content = part.content
                    if isinstance(content, str):
                        return content[:600]
                    return "; ".join(
                        f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in content[:6]
                    )[:800]
    return ""


def _param_line(param: DesignParam) -> str:
    if param.kind == "choice":
        choices = "|".join(o.value for o in param.options)
        return f"{param.name}={param.default} [{choices}]"
    if param.kind == "bool" or param.min is None or param.max is None:
        return f"{param.name}={param.default} ({param.kind})"
    return f"{param.name}={param.default:g} ({param.min:g}–{param.max:g})"


def _vec(values: tuple[int, int, int]) -> str:
    return " x ".join(str(v) for v in values)


def _repair_prompt(errors: list[str], origin: tuple[int, int, int]) -> str:
    return (
        "Die Engine lehnt das Modul ab. Korrigiere genau diese Fehler und liefere das "
        "vollständige Modul erneut. Koordinaten in den Meldungen sind global; der Modulursprung "
        f"liegt bei ({', '.join(str(v) for v in origin)}).\n" + "\n".join(f"- {e}" for e in errors)
    )


class Pipeline:
    """Runs the stages. One instance per process; the models come from ``build_models``."""

    def __init__(
        self,
        settings: Settings,
        models: Models | None,
        species: Mapping[str, str] | None = None,
        *,
        intake_model: Model | None = None,
        skeleton_model: Model | None = None,
        module_model: Model | None = None,
        docs_model: Model | None = None,
        engine: Engine | None = None,
    ) -> None:
        """``models`` may be ``None`` in test mode (``LLM_MODE=test``): the offline stand-ins
        answer, and no real model exists."""
        if settings.llm_mode == "test":
            from homeworking.modules.pipeline import offline

            stand_in: Models | None = None
            intake_model = intake_model or offline.intake_model()
            skeleton_model = skeleton_model or offline.skeleton_model()
            module_model = module_model or offline.module_model()
            docs_model = docs_model or offline.docs_model()
        else:
            stand_in = models
        # Small model for intake and modules; the larger designer model plans the skeleton
        # (ADR-0010).
        self._intake_model: Model = intake_model or _real(stand_in).fast
        self._skeleton_model: Model = skeleton_model or _real(stand_in).designer
        self._module_model: Model = module_model or _real(stand_in).fast
        self._docs_model: Model = docs_model or _real(stand_in).fast
        self._species = dict(species or {})
        self._engine = engine or default_engine()
        self._materials = digest(self._engine.catalog)
        self.intake_agent, self.skeleton_agent, self.module_agent, self.docs_agent = build_agents(
            self._intake_model, self._skeleton_model, self._module_model, self._docs_model
        )

    def _woods(self) -> str:
        return "Holzarten: " + ", ".join(self._species)

    @staticmethod
    def ready(spec: Spec) -> bool:
        return is_ready(spec)

    async def intake(
        self, spec: Spec, *, extract: bool = True, thorough: bool = False
    ) -> IntakeResult:
        """Read the text, then ask the few questions the engine still sees open.

        Without open questions no model is called. ``extract=False`` skips the model: used after
        the customer answered, when only the remaining questions need computing."""
        usage = StageUsage("intake")
        with _timed(usage):
            pending = open_questions(
                spec, self._species, limit=MAX_OPEN_FOR_MODEL, thorough=thorough
            )
            wording: dict[str, str] = {}
            if extract and pending:
                prompt = "\n".join(
                    [
                        _spec_line(spec),
                        "Offen: " + ", ".join(q.field for q in pending),
                        self._woods(),
                    ]
                )
                with _model_call(usage):
                    result = await self.intake_agent.run(prompt)
                usage.add(self._intake_model.model_name, result.usage)
                spec = apply_updates(spec, result.output.updates)
                wording = result.output.wording
            questions = [
                q.model_copy(update={"text": _word(wording.get(q.field), q.text)})
                for q in open_questions(spec, self._species, limit=MAX_QUESTIONS, thorough=thorough)
            ]
        return IntakeResult(spec, questions, usage)

    async def skeleton(
        self, spec: Spec, *, revise: tuple[SkeletonResult, list[str]] | None = None
    ) -> SkeletonResult:
        """Plan parameters and modules; one repair round with the engine's problems.

        ``revise`` = an accepted skeleton and the problems the merged modules showed: the model
        sees its own answer and these problems and plans again."""
        usage = StageUsage("skeleton")
        with _timed(usage):
            prompt = "\n".join([_spec_line(spec), self._woods()])
            failed: list[list[str]] = []
            history: list[ModelMessage] | None = None
            if revise is not None:
                previous, problems = revise
                history = previous.messages
                prompt = (
                    "Die Module passen mit diesem Gerüst nicht zusammen. Die Ursache liegt im "
                    "Gerüst (Parameter, Maße, Boxen). Korrigiere genau diese Fehler:\n"
                    + "\n".join(f"- {p}" for p in problems[:8])
                )
            for _ in range(SKELETON_ATTEMPTS):
                with _model_call(usage), capture_run_messages() as captured:
                    try:
                        result = await self.skeleton_agent.run(prompt, message_history=history)
                    except UnexpectedModelBehavior as exc:
                        # Invalid output after the framework's retries, or the output cap was
                        # hit. The call cost tokens; their number is unknown.
                        usage.requests += 1
                        why = _why(captured) or str(exc)[:200]
                        failed.append([f"Ausgabe unbrauchbar: {why}"])
                        if history is None:
                            prompt = f"{prompt}\nDie letzte Antwort war ungültig: {why}"
                        continue
                usage.add(self._skeleton_model.model_name, result.usage)
                skeleton = normalize(result.output, spec)
                problems = check_skeleton(skeleton, spec)
                if not problems:
                    return SkeletonResult(skeleton, usage, failed, result.all_messages())
                failed.append(problems)
                history = result.all_messages()
                prompt = (
                    "Die Engine lehnt das Gerüst ab. Korrigiere genau diese Fehler:\n"
                    + "\n".join(f"- {p}" for p in problems)
                )
            raise SkeletonRejectedError(failed[-1], usage)

    def _module_prompt(
        self, spec: Spec, skeleton: Skeleton, module: ModuleBrief, params: Mapping[str, ParamValue]
    ) -> str:
        """Stable parts first (catalog, brief, parameters), then what is specific to the module."""
        origin, size = module_box(module, params)
        neighbours = []
        for other in skeleton.modules:
            if other.id == module.id:
                continue
            o_origin, o_size = module_box(other, params)
            offset = (o_origin[0] - origin[0], o_origin[1] - origin[1], o_origin[2] - origin[2])
            neighbours.append(
                f"{other.id} ({other.title}): {other.role}; Box {_vec(o_size)} bei {_vec(offset)}"
            )
        head = f"Gerüst: {skeleton.object_type}, use={skeleton.use}, support={skeleton.support}" + (
            f", finish={skeleton.finish}" if skeleton.finish else ""
        )
        own = module.model_dump_json(
            include={"id", "title", "role", "size", "interfaces"}, exclude_defaults=True
        )
        return "\n".join(
            [
                self._materials,
                _spec_line(spec),
                head,
                "Parameter: " + "; ".join(_param_line(p) for p in skeleton.params),
                "Modul: " + own,
                f"Box (Standardwerte): {_vec(size)}",
                "Nachbarn: " + ("; ".join(neighbours) or "keine"),
            ]
        )

    async def _run_modules(
        self,
        prompts: Mapping[str, str],
        histories: dict[str, list[ModelMessage]],
        designs: dict[str, ModuleDesign],
        failures: dict[str, str],
        usage: StageUsage,
    ) -> None:
        """One model call per module, a few at a time. A module the model cannot deliver in valid
        form is left out; the merge reports it as missing and the next round asks again."""
        gate = asyncio.Semaphore(MODULE_PARALLEL)

        async def run(module_id: str, prompt: str) -> None:
            async with gate:
                with _model_call(usage), capture_run_messages() as captured:
                    try:
                        result = await self.module_agent.run(
                            prompt, message_history=histories.get(module_id)
                        )
                    except UnexpectedModelBehavior as exc:
                        # The call cost tokens; their number is unknown.
                        usage.requests += 1
                        failures[module_id] = _why(captured) or str(exc)[:300]
                        designs.pop(module_id, None)
                        histories.pop(module_id, None)
                        return
            usage.add(self._module_model.model_name, result.usage)
            failures.pop(module_id, None)
            designs[module_id] = result.output.model_copy(update={"module": module_id})
            histories[module_id] = result.all_messages()

        tasks = [asyncio.ensure_future(run(m, p)) for m, p in prompts.items()]
        try:
            await asyncio.gather(*tasks)
        except BaseException:
            # A provider error ends the stage: do not leave the other requests running (and
            # costing money) behind it.
            for task in tasks:
                task.cancel()
            raise

    async def modules(self, spec: Spec, skeleton: Skeleton) -> ModulesResult:
        """Design every module, merge, let the engine check; re-run only the modules it blames.

        The skeleton comes from the client in the API, so it is normalised and checked again."""
        usage = StageUsage("modules")
        with _timed(usage):
            skeleton = normalize(skeleton, spec)
            if problems := check_skeleton(skeleton, spec):
                raise ModulesRejectedError({SKELETON: problems}, usage)
            params = default_params(skeleton)
            briefs = {m.id: m for m in skeleton.modules}
            prompts = {
                m.id: self._module_prompt(spec, skeleton, m, params) for m in skeleton.modules
            }
            designs: dict[str, ModuleDesign] = {}
            histories: dict[str, list[ModelMessage]] = {}
            failures: dict[str, str] = {}
            repairs: list[dict[str, list[str]]] = []
            errors: dict[str, list[str]] = {}
            for attempt in range(MODULE_REPAIRS + 1):
                await self._run_modules(prompts, histories, designs, failures, usage)
                merged = await run_blocking(
                    lambda: check(self._engine, merge(skeleton, designs.values()), params)
                )
                errors = {
                    module: [*texts, *([failures[module]] if module in failures else [])]
                    for module, texts in merged.errors.items()
                }
                if merged.ok and merged.design is not None:
                    return ModulesResult(merged.design, designs, usage, repairs, merged.part_module)
                repairs.append(errors)
                if SKELETON in errors or attempt == MODULE_REPAIRS:
                    break
                prompts = {}
                for module, texts in errors.items():
                    local = [
                        t.replace("siehe list_materials", "siehe Katalog")
                        for t in localize(texts, module, merged.part_module)
                    ]
                    origin = module_box(briefs[module], params)[0]
                    if module in histories:
                        prompts[module] = _repair_prompt(local, origin)
                    else:  # nothing usable came back: ask again from the start
                        prompts[module] = (
                            self._module_prompt(spec, skeleton, briefs[module], params)
                            + "\nDie letzte Antwort war ungültig:\n"
                            + "\n".join(f"- {t}" for t in local)
                        )
            raise ModulesRejectedError(errors, usage)

    def _docs_prompt(self, spec: Spec, skeleton: Skeleton, built: ModulesResult) -> str:
        """Compact facts of the checked design; the engine's derived data stays out of it."""
        design = built.design
        modules = []
        for brief in skeleton.modules:
            parts = [
                f"{p.name} [{p.material}]"
                for p in design.parts
                if built.part_module.get(p.id) == brief.id
            ]
            modules.append(f"- {brief.id} ({brief.title}): {brief.role}; Teile: {', '.join(parts)}")
        hardware = ", ".join(h.item for h in design.hardware) or "keine"
        return "\n".join(
            [
                _spec_line(spec),
                f"Objekt: {skeleton.object_type} – {skeleton.summary} "
                f"(use={skeleton.use}, support={skeleton.support}"
                + (f", finish={skeleton.finish}" if skeleton.finish else "")
                + ")",
                "Parameter: " + "; ".join(_param_line(p) for p in skeleton.params),
                "Module:",
                *modules,
                "Beschläge: " + hardware,
            ]
        )

    async def document(self, spec: Spec, skeleton: Skeleton, built: ModulesResult) -> DocsResult:
        """Write the explanation and the build step texts of a checked design.

        The design never depends on this stage: if the model fails, or the engine rejects the
        steps it worded (e.g. a step names hardware the design does not have), the steps fall
        back to module title and role, and a missing explanation stays empty."""
        usage = StageUsage("docs")
        documentation: Documentation | None = None
        error: str | None = None
        with _timed(usage):
            try:
                with _model_call(usage):
                    result = await self.docs_agent.run(self._docs_prompt(spec, skeleton, built))
                usage.add(self._docs_model.model_name, result.usage)
                documentation = result.output
            except UnexpectedModelBehavior:
                pass
            except StageFailedError as exc:  # provider error or timeout: no texts, same design
                error = str(exc)
            worded = (
                {s.module: (s.title, s.text) for s in documentation.steps} if documentation else {}
            )
            params = default_params(skeleton)
            design = built.design
            for texts in (worded, {}):
                candidate = design.model_copy(
                    update={"steps": module_steps(skeleton, design, built.part_module, texts)}
                )
                try:
                    await run_blocking(self._engine.validate_design, candidate, params)
                except DesignRejectedError:
                    continue
                design = candidate
                break
        return DocsResult(
            design, documentation.explanation if documentation else None, usage, error
        )

    async def design(self, spec: Spec, *, on_stage: StageRecorder | None = None) -> DesignResult:
        """Skeleton, modules and documentation of a new design. Raises
        :class:`SkeletonRejectedError`, :class:`ModulesRejectedError` or, when a model call of
        a stage failed, :class:`StageFailedError`; ``on_stage`` sees every stage that ran, failed
        ones too."""

        async def seen(usage: StageUsage, error: str | None = None) -> None:
            if on_stage is not None and (usage.requests or error):
                await on_stage(usage, error)

        stages: list[StageUsage] = []
        try:
            planned = await self.skeleton(spec)
        except (SkeletonRejectedError, StageFailedError) as exc:
            await seen(exc.usage, str(exc))
            raise
        stages.append(planned.usage)
        await seen(planned.usage)
        revisions = 0
        while True:
            try:
                built = await self.modules(spec, planned.skeleton)
                break
            except StageFailedError as failed:
                await seen(failed.usage, str(failed))
                raise
            except ModulesRejectedError as exc:
                await seen(exc.usage, str(exc))
                problems = exc.errors.get(SKELETON)
                if not problems or revisions >= SKELETON_REVISIONS:
                    raise
                stages.append(exc.usage)
                revisions += 1
                try:
                    planned = await self.skeleton(spec, revise=(planned, problems))
                except (SkeletonRejectedError, StageFailedError) as rejected:
                    await seen(rejected.usage, str(rejected))
                    raise
                stages.append(planned.usage)
                await seen(planned.usage)
        stages.append(built.usage)
        await seen(built.usage)
        documented = await self.document(spec, planned.skeleton, built)
        await seen(documented.usage, documented.error)
        return DesignResult(
            documented.design,
            documented.explanation,
            planned.skeleton,
            [*stages, documented.usage],
        )
