"""Project use cases: create, execute commands, undo via replay, export."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from calc_engine.engine import ENGINE_VERSION, Engine
from construction_model.commands import (
    Command,
    CommandError,
    CreateProject,
    SelectVariant,
    Undo,
    apply_to_inputs,
    command_adapter,
    effective_commands,
)
from construction_model.diff import ModelDiff, diff_results
from construction_model.model import ParamValue, ProjectInputs, ProjectModel, Region
from homeworking.modules.projects.ports import (
    Actor,
    CommandRecord,
    ProjectListItem,
    ProjectRepository,
    StoredProject,
)


class ProjectNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class CommandOutcome:
    project: ProjectModel
    diff: ModelDiff
    seq: int


class ProjectService:
    def __init__(self, repository: ProjectRepository, engine: Engine) -> None:
        self._repo = repository
        self._engine = engine

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
            pack_version=self._engine.pack(pack_id).version,
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
        actor: Actor = "user",
        trace_id: str | None = None,
    ) -> CommandOutcome:
        command = CreateProject(pack_id=pack_id, title=title, params=params, region=region)
        self._engine.pack(pack_id)
        inputs = self._apply(None, command)
        result = self._engine.build(inputs)
        model = ProjectModel(id=uuid4(), inputs=inputs, result=result)
        diff = diff_results(None, result)
        await self._repo.add(
            owner_id, model, self._record(1, command, actor, pack_id, trace_id, diff)
        )
        return CommandOutcome(project=model, diff=diff, seq=1)

    async def get(self, owner_id: UUID, project_id: UUID) -> ProjectModel:
        return (await self._owned(owner_id, project_id)).model

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
        result = self._engine.build(inputs)
        model = old.model_copy(update={"inputs": inputs, "result": result})
        diff = diff_results(old.result, result)
        seq = await self._next_seq(project_id)
        await self._repo.append(
            model, self._record(seq, command, actor, inputs.pack_id, trace_id, diff)
        )
        return CommandOutcome(project=model, diff=diff, seq=seq)

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
        result = self._engine.build(inputs)
        model = stored.model.model_copy(update={"inputs": inputs, "result": result})
        diff = diff_results(stored.model.result, result)
        seq = (records[-1].seq if records else 0) + 1
        await self._repo.append(
            model, self._record(seq, Undo(), actor, inputs.pack_id, trace_id, diff)
        )
        return CommandOutcome(project=model, diff=diff, seq=seq)

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

    async def _next_seq(self, project_id: UUID) -> int:
        records = await self._repo.commands(project_id)
        return (records[-1].seq if records else 0) + 1
