"""Project use cases: create, execute commands, undo via replay, export."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import anyio

from calc_engine.assembly.derive import DESIGN_PACK_ID
from calc_engine.assembly.templates import template
from calc_engine.engine import ENGINE_VERSION, Engine, UnknownPackError
from construction_model.assembly import AssemblyDesign
from construction_model.commands import (
    Command,
    CommandError,
    CreateProject,
    ReplaceInputs,
    SelectVariant,
    Undo,
    apply_to_inputs,
    can_undo,
    command_adapter,
    effective_commands,
)
from construction_model.diff import ModelDiff, diff_results
from construction_model.model import (
    ConstructionResult,
    Origin,
    ParamValue,
    ProjectInputs,
    ProjectModel,
    Region,
)
from homeworking.modules.projects.ports import (
    Actor,
    CommandRecord,
    ProjectListItem,
    ProjectRepository,
    StoredProject,
)


class ProjectNotFoundError(LookupError):
    pass


class VersionNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class CommandOutcome:
    project: ProjectModel
    diff: ModelDiff
    seq: int
    can_undo: bool


# Rebuilt earlier versions; the command log is append-only, so (project, seq) never changes.
VERSION_CACHE_SIZE = 64


class ProjectService:
    def __init__(self, repository: ProjectRepository, engine: Engine) -> None:
        self._repo = repository
        self._engine = engine
        self._versions: OrderedDict[tuple[UUID, int], tuple[ProjectInputs, ConstructionResult]] = (
            OrderedDict()
        )

    async def _build(self, inputs: ProjectInputs) -> ConstructionResult:
        """Run the engine in a worker thread: it is CPU-bound and would block the event loop
        (and with it every other request and agent stream) for its whole duration."""
        return await anyio.to_thread.run_sync(self._engine.build, inputs)

    @property
    def engine(self) -> Engine:
        return self._engine

    def _apply(self, inputs: ProjectInputs | None, command: Command) -> ProjectInputs:
        overrides = (
            self._engine.variant_overrides(inputs)
            if inputs is not None and isinstance(command, SelectVariant)
            else None
        )
        return apply_to_inputs(inputs, command, variant_overrides=overrides)

    def _record(
        self,
        seq: int,
        command: Command,
        actor: Actor,
        pack_id: str,
        trace_id: str | None,
        diff: ModelDiff,
    ) -> CommandRecord:
        return CommandRecord(
            seq=seq,
            command=command,
            actor=actor,
            engine_version=ENGINE_VERSION,
            pack_version=self._engine.pack_version(pack_id),
            llm_trace_id=trace_id,
            diff=diff,
        )

    async def create(
        self,
        owner_id: UUID,
        *,
        pack_id: str,
        title: str,
        params: dict[str, ParamValue],
        region: Region | None = None,
        design: AssemblyDesign | None = None,
        actor: Actor = "user",
        trace_id: str | None = None,
    ) -> CommandOutcome:
        command = CreateProject(
            pack_id=pack_id, title=title, params=params, region=region, design=design
        )
        self._engine.ensure_known(pack_id, design)
        inputs = self._apply(None, command)
        result = await self._build(inputs)
        model = ProjectModel(id=uuid4(), inputs=inputs, result=result)
        diff = diff_results(None, result)
        await self._repo.add(
            owner_id, model, self._record(1, command, actor, pack_id, trace_id, diff)
        )
        return CommandOutcome(project=model, diff=diff, seq=1, can_undo=False)

    async def create_from_template(
        self,
        owner_id: UUID,
        *,
        template_key: str,
        title: str | None = None,
        params: dict[str, ParamValue] | None = None,
        region: Region | None = None,
        untreated: bool = False,
        replace_project_id: UUID | None = None,
        actor: Actor = "user",
        trace_id: str | None = None,
    ) -> CommandOutcome:
        """Create a free-form project from a curated design template (ADR-0004).

        With ``replace_project_id`` the template becomes a new version of that project instead.
        """
        try:
            tpl = template(template_key)
        except KeyError:
            raise UnknownPackError(template_key) from None
        design = tpl.design.model_copy(update={"finish": None}) if untreated else tpl.design
        if replace_project_id is not None:
            return await self.replan(
                owner_id,
                replace_project_id,
                pack_id=DESIGN_PACK_ID,
                title=title or tpl.title,
                params=params or {},
                design=design,
                actor=actor,
                trace_id=trace_id,
            )
        return await self.create(
            owner_id,
            pack_id=DESIGN_PACK_ID,
            title=title or tpl.title,
            params=params or {},
            region=region,
            design=design,
            actor=actor,
            trace_id=trace_id,
        )

    async def replan(
        self,
        owner_id: UUID,
        project_id: UUID,
        *,
        pack_id: str,
        title: str,
        params: dict[str, ParamValue],
        design: AssemblyDesign | None = None,
        actor: Actor = "user",
        trace_id: str | None = None,
    ) -> CommandOutcome:
        """Plan an existing project anew (other pack, template or design) as its next version.

        Region, user prices and user notes stay; AI explanations belong to the old construction.
        """
        self._engine.ensure_known(pack_id, design)
        current = (await self._owned(owner_id, project_id)).model.inputs
        inputs = ProjectInputs(
            title=title,
            pack_id=pack_id,
            params=dict(params),
            region=current.region,
            design=design,
            prices=current.prices,
            notes=[n for n in current.notes if n.origin is not Origin.AI],
        )
        return await self.execute(
            owner_id, project_id, ReplaceInputs(inputs=inputs), actor=actor, trace_id=trace_id
        )

    async def version(self, owner_id: UUID, project_id: UUID, seq: int) -> ProjectModel:
        """The project as it was right after log entry ``seq`` (deterministic replay)."""
        stored = await self._owned(owner_id, project_id)
        key = (project_id, seq)
        if (cached := self._versions.get(key)) is None:
            records = [r for r in await self._repo.commands(project_id) if r.seq <= seq]
            if not records or records[-1].seq != seq:
                raise VersionNotFoundError(seq)
            inputs: ProjectInputs | None = None
            for _, command in effective_commands((r.seq, r.command) for r in records):
                inputs = self._apply(inputs, command)
            assert inputs is not None
            cached = (inputs, await self._build(inputs))
            self._versions[key] = cached
            if len(self._versions) > VERSION_CACHE_SIZE:
                self._versions.popitem(last=False)
        else:
            self._versions.move_to_end(key)
        return stored.model.model_copy(update={"inputs": cached[0], "result": cached[1]})

    async def restore(
        self,
        owner_id: UUID,
        project_id: UUID,
        seq: int,
        *,
        actor: Actor = "user",
        trace_id: str | None = None,
    ) -> CommandOutcome:
        """Make an earlier version current again; it is appended, so no history is lost."""
        old = await self.version(owner_id, project_id, seq)
        return await self.execute(
            owner_id,
            project_id,
            ReplaceInputs(inputs=old.inputs, restored_seq=seq),
            actor=actor,
            trace_id=trace_id,
        )

    async def get(self, owner_id: UUID, project_id: UUID) -> ProjectModel:
        return (await self._owned(owner_id, project_id)).model

    async def view(self, owner_id: UUID, project_id: UUID) -> tuple[ProjectModel, bool, int]:
        """Return the project, whether it has something to undo and its log position."""
        stored = await self._owned(owner_id, project_id)
        records = await self._repo.commands(project_id)
        seq = records[-1].seq if records else 0
        return stored.model, can_undo([r.command for r in records]), seq

    async def list_projects(self, owner_id: UUID) -> list[ProjectListItem]:
        return await self._repo.list_for_owner(owner_id)

    async def history(self, owner_id: UUID, project_id: UUID) -> list[CommandRecord]:
        await self._owned(owner_id, project_id)
        return await self._repo.commands(project_id)

    async def execute(
        self,
        owner_id: UUID,
        project_id: UUID,
        command: Command,
        *,
        actor: Actor = "user",
        trace_id: str | None = None,
    ) -> CommandOutcome:
        if isinstance(command, CreateProject):
            raise CommandError("Use create() for new projects")
        if isinstance(command, Undo):
            return await self.undo(owner_id, project_id, actor=actor, trace_id=trace_id)
        stored = await self._owned(owner_id, project_id)
        old = stored.model
        inputs = self._apply(old.inputs, command)
        result = await self._build(inputs)
        model = old.model_copy(update={"inputs": inputs, "result": result})
        diff = diff_results(old.result, result)
        records = await self._repo.commands(project_id)
        seq = (records[-1].seq if records else 0) + 1
        await self._repo.append(
            model, self._record(seq, command, actor, inputs.pack_id, trace_id, diff)
        )
        undoable = can_undo([*(r.command for r in records), command])
        return CommandOutcome(project=model, diff=diff, seq=seq, can_undo=undoable)

    async def undo(
        self,
        owner_id: UUID,
        project_id: UUID,
        *,
        actor: Actor = "user",
        trace_id: str | None = None,
    ) -> CommandOutcome:
        stored = await self._owned(owner_id, project_id)
        records = await self._repo.commands(project_id)
        log = [(r.seq, r.command) for r in records] + [(0, Undo())]
        effective = effective_commands(log)
        inputs: ProjectInputs | None = None
        for _, command in effective:
            inputs = self._apply(inputs, command)
        assert inputs is not None
        result = await self._build(inputs)
        model = stored.model.model_copy(update={"inputs": inputs, "result": result})
        diff = diff_results(stored.model.result, result)
        seq = (records[-1].seq if records else 0) + 1
        await self._repo.append(
            model, self._record(seq, Undo(), actor, inputs.pack_id, trace_id, diff)
        )
        return CommandOutcome(project=model, diff=diff, seq=seq, can_undo=len(effective) > 1)

    async def delete(self, owner_id: UUID, project_id: UUID) -> None:
        await self._owned(owner_id, project_id)
        await self._repo.delete(project_id)

    async def export(self, owner_id: UUID, project_id: UUID) -> dict[str, Any]:
        """GDPR Art. 20 / Data Act friendly export of model and full command log."""
        stored = await self._owned(owner_id, project_id)
        records = await self._repo.commands(project_id)
        return {
            "format": "homeworking.project-export",
            "format_version": 1,
            "project": stored.model.model_dump(mode="json"),
            "commands": [
                {
                    "seq": r.seq,
                    "actor": r.actor,
                    "engine_version": r.engine_version,
                    "pack_version": r.pack_version,
                    "llm_trace_id": r.llm_trace_id,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "command": command_adapter.dump_python(r.command, mode="json"),
                }
                for r in records
            ],
        }

    async def _owned(self, owner_id: UUID, project_id: UUID) -> StoredProject:
        stored = await self._repo.get(project_id)
        if stored is None or stored.owner_id != owner_id:
            raise ProjectNotFoundError(project_id)
        return stored
