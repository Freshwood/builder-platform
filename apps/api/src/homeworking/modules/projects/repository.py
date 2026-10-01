"""SQLAlchemy adapter for :class:`ProjectRepository`."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from construction_model.commands import command_adapter
from construction_model.diff import ModelDiff
from construction_model.model import ProjectModel
from homeworking.db.schema import ProjectCommandRow, ProjectRow
from homeworking.modules.projects.ports import CommandRecord, ProjectListItem, StoredProject

# Upcasters migrate stored documents from older schema versions: {from_version: fn}.
UPCASTERS: dict[int, Any] = {}


def load_model(document: dict[str, Any]) -> ProjectModel:
    version = int(document.get("schema_version", 1))
    while version in UPCASTERS:
        document = UPCASTERS[version](document)
        version = int(document["schema_version"])
    return ProjectModel.model_validate(document)


def _to_record(row: ProjectCommandRow) -> CommandRecord:
    return CommandRecord(
        seq=row.seq,
        command=command_adapter.validate_python(row.command),
        actor="agent" if row.actor == "agent" else "user",
        engine_version=row.engine_version,
        pack_version=row.pack_version,
        llm_trace_id=row.llm_trace_id,
        diff=ModelDiff.model_validate(row.diff) if row.diff else None,
        created_at=row.created_at,
    )


def _command_row(project_id: UUID, record: CommandRecord) -> ProjectCommandRow:
    return ProjectCommandRow(
        project_id=project_id,
        seq=record.seq,
        command=command_adapter.dump_python(record.command, mode="json"),
        actor=record.actor,
        llm_trace_id=record.llm_trace_id,
        engine_version=record.engine_version,
        pack_version=record.pack_version,
        diff=record.diff.model_dump(mode="json") if record.diff else None,
    )


class SqlProjectRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def add(self, owner_id: UUID, model: ProjectModel, record: CommandRecord) -> None:
        async with self._sessions.begin() as session:
            session.add(
                ProjectRow(
                    id=model.id,
                    owner_id=owner_id,
                    title=model.inputs.title,
                    pack_id=model.inputs.pack_id,
                    schema_version=model.schema_version,
                    model=model.model_dump(mode="json"),
                )
            )
            await session.flush()
            session.add(_command_row(model.id, record))

    async def get(self, project_id: UUID) -> StoredProject | None:
        async with self._sessions() as session:
            row = await session.get(ProjectRow, project_id)
            if row is None:
                return None
            return StoredProject(
                owner_id=row.owner_id, model=load_model(row.model), updated_at=row.updated_at
            )

    async def list_for_owner(self, owner_id: UUID) -> list[ProjectListItem]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(ProjectRow)
                .where(ProjectRow.owner_id == owner_id)
                .order_by(ProjectRow.updated_at.desc(), ProjectRow.created_at.desc())
            )
            return [
                ProjectListItem(
                    id=row.id,
                    title=row.title,
                    pack_id=row.pack_id,
                    summary=str(row.model.get("result", {}).get("summary", "")),
                    updated_at=row.updated_at,
                )
                for row in rows
            ]

    async def append(self, model: ProjectModel, record: CommandRecord) -> None:
        async with self._sessions.begin() as session:
            row = await session.get(ProjectRow, model.id)
            if row is None:
                raise LookupError(model.id)
            row.title = model.inputs.title
            row.schema_version = model.schema_version
            row.model = model.model_dump(mode="json")
            session.add(_command_row(model.id, record))

    async def commands(self, project_id: UUID) -> list[CommandRecord]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(ProjectCommandRow)
                .where(ProjectCommandRow.project_id == project_id)
                .order_by(ProjectCommandRow.seq)
            )
            return [_to_record(row) for row in rows]

    async def delete(self, project_id: UUID) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                delete(ProjectCommandRow).where(ProjectCommandRow.project_id == project_id)
            )
            await session.execute(delete(ProjectRow).where(ProjectRow.id == project_id))
