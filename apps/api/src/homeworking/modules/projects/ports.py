"""Ports and records of the projects module."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from construction_model.commands import Command
from construction_model.diff import ModelDiff
from construction_model.model import ProjectModel

Actor = Literal["user", "agent"]


@dataclass(frozen=True)
class CommandRecord:
    seq: int
    command: Command
    actor: Actor
    engine_version: str
    pack_version: str
    llm_trace_id: str | None = None
    diff: ModelDiff | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class StoredProject:
    owner_id: UUID
    model: ProjectModel
    updated_at: datetime | None


@dataclass(frozen=True)
class ProjectListItem:
    id: UUID
    title: str
    pack_id: str
    summary: str
    updated_at: datetime | None


class ProjectRepository(Protocol):
    async def add(self, owner_id: UUID, model: ProjectModel, record: CommandRecord) -> None: ...

    async def get(self, project_id: UUID) -> StoredProject | None: ...

    async def list_for_owner(self, owner_id: UUID) -> list[ProjectListItem]: ...

    async def append(self, model: ProjectModel, record: CommandRecord) -> None: ...

    async def commands(self, project_id: UUID) -> list[CommandRecord]: ...

    async def delete(self, project_id: UUID) -> None: ...
