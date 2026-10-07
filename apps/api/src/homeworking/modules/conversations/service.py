"""Agent runs are stored completely: they cost money and are the provenance of AI results.

The chat of a project is rebuilt from its runs, so it survives reloads and device changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from homeworking.db.schema import AgentRunRow

RunStatus = Literal["completed", "failed", "cancelled"]


@dataclass(frozen=True)
class AgentRun:
    trace_id: str
    owner_id: UUID
    chat_id: str | None
    project_id: UUID | None
    status: RunStatus
    model: str
    prompt_version: str
    ui_messages: list[dict[str, Any]]
    model_messages: list[Any] | None = None
    design_attempts: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] | None = None
    error: str | None = None


class ConversationService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def record(self, run: AgentRun) -> None:
        """Store a finished run and attach the chat's earlier project-less turns to its project."""
        async with self._sessions.begin() as session:
            session.add(
                AgentRunRow(
                    id=uuid4(),
                    trace_id=run.trace_id,
                    owner_id=run.owner_id,
                    chat_id=run.chat_id,
                    project_id=run.project_id,
                    status=run.status,
                    model=run.model,
                    prompt_version=run.prompt_version,
                    ui_messages=run.ui_messages,
                    model_messages=run.model_messages,
                    design_attempts=run.design_attempts,
                    usage=run.usage,
                    error=run.error[:2000] if run.error else None,
                    # Set here: SQLite's server default has only second resolution (chat order).
                    created_at=datetime.now(UTC),
                )
            )
            if run.project_id is not None and run.chat_id is not None:
                # Questions asked before the first project existed belong to its chat, too.
                await session.execute(
                    update(AgentRunRow)
                    .where(
                        AgentRunRow.owner_id == run.owner_id,
                        AgentRunRow.chat_id == run.chat_id,
                        AgentRunRow.project_id.is_(None),
                    )
                    .values(project_id=run.project_id)
                )

    async def chat(self, owner_id: UUID, project_id: UUID) -> list[dict[str, Any]]:
        """UI messages of all turns about a project, oldest first."""
        async with self._sessions() as session:
            rows = await session.scalars(
                select(AgentRunRow.ui_messages)
                .where(AgentRunRow.owner_id == owner_id, AgentRunRow.project_id == project_id)
                .order_by(AgentRunRow.created_at, AgentRunRow.id)
            )
            return [message for messages in rows for message in messages]
