"""Project endpoints."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from calc_engine.assembly.templates import templates
from calc_engine.pack import PackDescriptor
from construction_model.assembly import AssemblyDesign
from construction_model.commands import EditCommand, command_adapter
from construction_model.diff import ModelDiff
from construction_model.model import ParamValue, ProjectModel, Region
from homeworking.api.deps import ContainerDep, UserDep
from homeworking.modules.compliance.disclosure import (
    AI_CHAT_DISCLOSURE,
    DOCUMENT_NOTICES,
    NOTICES_VERSION,
)
from homeworking.modules.documents.pdf import render_pdf
from homeworking.modules.drawings.svg import render_svg
from homeworking.modules.projects.service import CommandOutcome

router = APIRouter(prefix="/api", tags=["projects"])
log = logging.getLogger("homeworking.documents")


class CreateProjectRequest(BaseModel):
    pack_id: str = Field(
        description="Construction pack id, 'design' for a free-form design or 'template'"
    )
    title: str = Field(min_length=1, max_length=200)
    params: dict[str, ParamValue] = Field(default_factory=dict)
    region: Region | None = None
    design: AssemblyDesign | None = Field(None, description="Required for pack_id 'design'")
    template_key: str | None = Field(None, description="Required for pack_id 'template'")


class TemplateEntry(BaseModel):
    key: str
    title: str
    description: str


class CommandRequest(BaseModel):
    command: EditCommand


class ProjectView(BaseModel):
    project: ProjectModel
    can_undo: bool


class CommandResponse(ProjectView):
    diff: ModelDiff
    seq: int


class ProjectListEntry(BaseModel):
    id: UUID
    title: str
    pack_id: str
    summary: str
    updated_at: datetime | None


class HistoryEntry(BaseModel):
    seq: int
    actor: str
    command: dict[str, Any]
    engine_version: str
    created_at: datetime | None


class MeResponse(BaseModel):
    id: UUID
    is_guest: bool


class LegalNotices(BaseModel):
    version: str
    ai_disclosure: str
    document_notices: list[str]


def _command_response(outcome: CommandOutcome) -> CommandResponse:
    return CommandResponse(
        project=outcome.project, can_undo=outcome.can_undo, diff=outcome.diff, seq=outcome.seq
    )


@router.get("/me", response_model=MeResponse)
async def me(user: UserDep) -> MeResponse:
    return MeResponse(id=user.id, is_guest=user.is_guest)


@router.get("/notices", response_model=LegalNotices)
async def notices() -> LegalNotices:
    return LegalNotices(
        version=NOTICES_VERSION,
        ai_disclosure=AI_CHAT_DISCLOSURE,
        document_notices=DOCUMENT_NOTICES,
    )


@router.get("/packs", response_model=list[PackDescriptor])
async def list_packs(container: ContainerDep) -> list[PackDescriptor]:
    return container.engine.describe_packs()


@router.get("/templates", response_model=list[TemplateEntry])
async def list_templates() -> list[TemplateEntry]:
    return [
        TemplateEntry(key=t.key, title=t.title, description=t.description)
        for t in templates().values()
    ]


@router.get("/projects", response_model=list[ProjectListEntry])
async def list_projects(container: ContainerDep, user: UserDep) -> list[ProjectListEntry]:
    items = await container.projects.list_projects(user.id)
    return [
        ProjectListEntry(
            id=i.id, title=i.title, pack_id=i.pack_id, summary=i.summary, updated_at=i.updated_at
        )
        for i in items
    ]


@router.post("/projects", response_model=CommandResponse, status_code=201)
async def create_project(
    body: CreateProjectRequest, container: ContainerDep, user: UserDep
) -> CommandResponse:
    if body.pack_id == "template":
        if not body.template_key:
            raise HTTPException(status_code=422, detail="template_key fehlt")
        outcome = await container.projects.create_from_template(
            user.id,
            template_key=body.template_key,
            title=body.title,
            params=body.params,
            region=body.region,
        )
    else:
        outcome = await container.projects.create(
            user.id,
            pack_id=body.pack_id,
            title=body.title,
            params=body.params,
            region=body.region,
            design=body.design,
        )
    return _command_response(outcome)


@router.get("/projects/{project_id}", response_model=ProjectView)
async def get_project(project_id: UUID, container: ContainerDep, user: UserDep) -> ProjectView:
    model, undoable = await container.projects.view(user.id, project_id)
    return ProjectView(project=model, can_undo=undoable)


@router.post("/projects/{project_id}/commands", response_model=CommandResponse)
async def execute_command(
    project_id: UUID, body: CommandRequest, container: ContainerDep, user: UserDep
) -> CommandResponse:
    return _command_response(await container.projects.execute(user.id, project_id, body.command))


@router.post("/projects/{project_id}/undo", response_model=CommandResponse)
async def undo(project_id: UUID, container: ContainerDep, user: UserDep) -> CommandResponse:
    return _command_response(await container.projects.undo(user.id, project_id))


@router.get("/projects/{project_id}/history", response_model=list[HistoryEntry])
async def history(project_id: UUID, container: ContainerDep, user: UserDep) -> list[HistoryEntry]:
    records = await container.projects.history(user.id, project_id)
    return [
        HistoryEntry(
            seq=r.seq,
            actor=r.actor,
            command=command_adapter.dump_python(r.command, mode="json"),
            engine_version=r.engine_version,
            created_at=r.created_at,
        )
        for r in records
    ]


@router.get(
    "/projects/{project_id}/drawings/{view}.svg",
    response_class=Response,
    responses={200: {"content": {"image/svg+xml": {}}}},
)
async def drawing(project_id: UUID, view: str, container: ContainerDep, user: UserDep) -> Response:
    model = await container.projects.get(user.id, project_id)
    for d in model.result.drawings:
        if d.view == view:
            return Response(render_svg(d, element_id=f"drawing-{view}"), media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="Unknown view")


@router.get(
    "/projects/{project_id}/document.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def document(project_id: UUID, container: ContainerDep, user: UserDep) -> Response:
    model = await container.projects.get(user.id, project_id)
    try:
        pdf = await run_in_threadpool(render_pdf, model)
    except Exception:
        # A plain-text 500 would make the browser save an unreadable "document.txt".
        log.exception("pdf_render_failed", extra={"project_id": str(project_id)})
        return JSONResponse(
            {"detail": "Das PDF konnte nicht erstellt werden. Bitte versuche es erneut."},
            status_code=500,
        )
    filename = f"homeworking-{model.inputs.pack_id}-{str(model.id)[:8]}.pdf"
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/projects/{project_id}/export")
async def export(project_id: UUID, container: ContainerDep, user: UserDep) -> dict[str, Any]:
    return await container.projects.export(user.id, project_id)


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: UUID, container: ContainerDep, user: UserDep) -> Response:
    await container.projects.delete(user.id, project_id)
    return Response(status_code=204)
