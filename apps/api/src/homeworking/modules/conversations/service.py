"""Agent runs are stored completely: they cost money and are the provenance of AI results.

The chat of a project is rebuilt from its runs, so it survives reloads and device changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from homeworking.db.schema import AgentRunRow

RunStatus = Literal["completed", "failed", "cancelled"]

# Older turns add little for the next answer but cost tokens on every request.
HISTORY_MAX_RUNS = 20


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
    prompt_fingerprint: str | None = None
    safety_rules_version: str | None = None
    model_role: str | None = None
    routing_reason: str | None = None
    duration_ms: int | None = None


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
                    prompt_fingerprint=run.prompt_fingerprint,
                    safety_rules_version=run.safety_rules_version,
                    model_role=run.model_role,
                    routing_reason=run.routing_reason,
                    duration_ms=run.duration_ms,
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

    async def history(
        self, owner_id: UUID, *, chat_id: str | None, project_id: UUID | None
    ) -> list[ModelMessage]:
        """Model messages of the latest completed turns of a chat or project, oldest first.

        This is the trusted conversation history for the next turn: the browser only sends its
        new message, so it neither re-uploads the whole chat nor can it inject tool results.
        """
        scopes = []
        if chat_id is not None:
            scopes.append(AgentRunRow.chat_id == chat_id)
        if project_id is not None:
            scopes.append(AgentRunRow.project_id == project_id)
        if not scopes:
            return []
        async with self._sessions() as session:
            rows = await session.scalars(
                select(AgentRunRow.model_messages)
                .where(
                    AgentRunRow.owner_id == owner_id,
                    AgentRunRow.status == "completed",
                    AgentRunRow.model_messages.is_not(None),
                    or_(*scopes),
                )
                .order_by(AgentRunRow.created_at.desc(), AgentRunRow.id.desc())
                .limit(HISTORY_MAX_RUNS)
            )
            runs = list(rows)
        return [
            message
            for run in reversed(runs)
            if run  # JSON null on some backends
            for message in ModelMessagesTypeAdapter.validate_python(run)
        ]
