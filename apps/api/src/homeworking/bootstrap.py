"""Composition root: wires ports to adapters."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from calc_engine.engine import Engine, default_engine
from homeworking.db.schema import Base
from homeworking.db.session import make_engine, make_session_factory
from homeworking.modules.agent.model import build_model
from homeworking.modules.agent.tools import AgentDeps, build_agent
from homeworking.modules.identity.service import IdentityProvider, SqlGuestIdentityProvider
from homeworking.modules.projects.repository import SqlProjectRepository
from homeworking.modules.projects.service import ProjectService
from homeworking.settings import Settings


@dataclass
class Container:
    settings: Settings
    db: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    engine: Engine
    projects: ProjectService
    identity: IdentityProvider
    agent: Agent[AgentDeps, str]
    model_name: str

    async def create_schema(self) -> None:
        """Create tables directly (tests / SQLite dev). Production uses Alembic."""
        async with self.db.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.db.dispose()


def build_container(settings: Settings, engine: Engine | None = None) -> Container:
    db = make_engine(settings.database_url)
    sessions = make_session_factory(db)
    calc = engine or default_engine()
    model = build_model(settings)
    return Container(
        settings=settings,
        db=db,
        sessions=sessions,
        engine=calc,
        projects=ProjectService(SqlProjectRepository(sessions), calc),
        identity=SqlGuestIdentityProvider(sessions),
        agent=build_agent(model),
        model_name=model.model_name,
    )
