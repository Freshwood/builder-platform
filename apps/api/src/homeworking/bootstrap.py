"""Composition root: wires ports to adapters."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from homeworking.calc_engine.engine import Engine, default_engine
from homeworking.db.schema import Base
from homeworking.db.session import make_engine, make_session_factory
from homeworking.modules.agent.deps import AgentDeps
from homeworking.modules.agent.tools import build_agent
from homeworking.modules.conversations.service import ConversationService
from homeworking.modules.identity.service import IdentityProvider, SqlGuestIdentityProvider
from homeworking.modules.llm.model import Models, OfflineFactory, build_models
from homeworking.modules.pipeline.stages import Pipeline
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
    conversations: ConversationService
    agent: Agent[AgentDeps, str]
    models: Models
    pipeline: Pipeline

    async def create_schema(self) -> None:
        """Create tables directly (tests / SQLite dev). Production uses Alembic."""
        async with self.db.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.db.dispose()


def _offline_factory(settings: Settings) -> OfflineFactory | None:
    """The offline chat model, imported only when it is used (``LLM_MODE=test``)."""
    if settings.llm_mode != "test":
        return None
    from homeworking.modules.agent.offline import offline_model

    return offline_model


def build_container(settings: Settings, engine: Engine | None = None) -> Container:
    db = make_engine(settings.database_url)
    sessions = make_session_factory(db)
    calc = engine or default_engine()
    models = build_models(settings, offline=_offline_factory(settings))
    return Container(
        settings=settings,
        db=db,
        sessions=sessions,
        engine=calc,
        projects=ProjectService(SqlProjectRepository(sessions), calc),
        identity=SqlGuestIdentityProvider(sessions),
        conversations=ConversationService(sessions),
        agent=build_agent(models.designer),
        models=models,
        pipeline=Pipeline(
            settings,
            # In test mode the pipeline brings its own offline stage models.
            None if settings.llm_mode == "test" else build_models(settings, stages=True),
            {k: m.label for k, m in calc.catalog.lumber_species().items()},
        ),
    )
