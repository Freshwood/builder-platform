"""FastAPI application factory."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from calc_engine.engine import ParameterError, UnknownPackError
from construction_model.commands import CommandError
from homeworking.api import chat, projects
from homeworking.bootstrap import Container, build_container
from homeworking.modules.documents.pdf import warm_up as warm_up_pdf
from homeworking.modules.projects.service import ProjectNotFoundError
from homeworking.settings import Settings, get_settings


def create_app(
    settings: Settings | None = None,
    container: Container | None = None,
    *,
    create_schema: bool = False,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = container or build_container(settings)
        if create_schema or settings.auto_create_schema:
            await app.state.container.create_schema()
        # Warm up PDF rendering in the background; startup does not wait for it.
        warm_up_task = asyncio.create_task(asyncio.to_thread(warm_up_pdf))
        yield
        warm_up_task.cancel()
        await app.state.container.close()

    app = FastAPI(
        title="Homeworking API",
        version="0.1.0",
        description="Bauvorhaben als veränderbares, berechenbares Projektmodell.",
        lifespan=lifespan,
        # Readable operation ids for the generated TypeScript client.
        generate_unique_id_function=lambda route: route.name,
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret.get_secret_value(),
        session_cookie="hw_session",
        max_age=60 * 60 * 24 * 180,
        same_site="lax",
        https_only=settings.secure_cookies,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["content-type"],
    )

    @app.exception_handler(ProjectNotFoundError)
    async def _not_found(_: Request, __: ProjectNotFoundError) -> JSONResponse:
        return JSONResponse({"detail": "Projekt nicht gefunden"}, status_code=404)

    @app.exception_handler(UnknownPackError)
    async def _unknown_pack(_: Request, exc: UnknownPackError) -> JSONResponse:
        return JSONResponse({"detail": f"Unbekanntes Pack {exc}"}, status_code=404)

    @app.exception_handler(ParameterError)
    async def _bad_params(_: Request, exc: ParameterError) -> JSONResponse:
        return JSONResponse({"detail": exc.errors}, status_code=422)

    @app.exception_handler(CommandError)
    async def _bad_command(_: Request, exc: CommandError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.get("/api/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(projects.router)
    app.include_router(chat.router)
    return app


app = create_app()
