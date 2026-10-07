"""Project endpoints."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from calc_engine.assembly.templates import templates
from calc_engine.pack import PackDescriptor
from construction_model.assembly import AssemblyDesign
from construction_model.commands import (
    AddNote,
    ChangeParameterBy,
    Command,
    CreateProject,
    EditCommand,
    Rename,
    ReplaceDesign,
    ReplaceInputs,
    SelectVariant,
    SetParameters,
    SetPrice,
    SetRegion,
    Undo,
    command_adapter,
)
from construction_model.diff import ModelDiff
from construction_model.model import Origin, ParamValue, ProjectModel, Region
from homeworking.api.deps import ContainerDep, UserDep
from homeworking.modules.compliance.disclosure import (
    AI_CHAT_DISCLOSURE,
    DOCUMENT_NOTICES,
    NOTICES_VERSION,
)
from homeworking.modules.documents.pdf import render_pdf
from homeworking.modules.drawings.svg import render_svg
from homeworking.modules.projects.ports import CommandRecord
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


class VersionEntry(BaseModel):
    seq: int
    label: str = Field(description="German description of the change")
    actor: str
    created_at: datetime | None
    material_cost: tuple[Decimal, Decimal] | None = Field(
        None, description="Material cost range (EUR) of the project after this change"
    )
    construction: bool = Field(description="Whether the change replaced the construction")
    current: bool


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


def _changes(record: CommandRecord, labels: dict[str, str]) -> str:
    changes = record.diff.params if record.diff else []
    return ", ".join(f"{labels.get(c.name, c.name)} {c.before} → {c.after}" for c in changes)


def _version_label(record: CommandRecord, labels: dict[str, str]) -> str:
    command: Command = record.command
    match command:
        case CreateProject(title=title):
            return f"Projekt „{title}“ erstellt"
        case SetParameters() | ChangeParameterBy():
            changes = _changes(record, labels)
            return f"Geändert: {changes}" if changes else "Parameter geändert"
        case SelectVariant(variant_key=key):
            return f"Variante „{key}“ gewählt"
        case Rename(title=title):
            return f"Umbenannt in „{title}“"
        case SetRegion():
            return "Region geändert"
        case AddNote():
            return "Notiz hinzugefügt"
        case ReplaceDesign():
            return "Neuer Entwurf"
        case SetPrice():
            return "Eigener Preis eingetragen"
        case ReplaceInputs(restored_seq=seq, inputs=inputs):
            return f"Version {seq} wiederhergestellt" if seq else f"Neu geplant: {inputs.title}"
        case Undo():
            return "Rückgängig gemacht"
    return command.type  # pragma: no cover


@router.get("/projects/{project_id}/versions", response_model=list[VersionEntry])
async def versions(project_id: UUID, container: ContainerDep, user: UserDep) -> list[VersionEntry]:
    """Every log entry is a version that can be viewed and restored (newest first)."""
    model = await container.projects.get(user.id, project_id)
    labels = {p.name: p.label for p in model.result.param_specs}
    # An AI explanation is stored right after the construction it explains: same version.
    records = [
        r
        for r in await container.projects.history(user.id, project_id)
        if not (isinstance(r.command, AddNote) and r.command.origin is Origin.AI)
    ]
    last = records[-1].seq if records else 0
    return [
        VersionEntry(
            seq=r.seq,
            label=_version_label(r, labels),
            actor=r.actor,
            created_at=r.created_at,
            material_cost=r.diff.material_cost_after if r.diff else None,
            construction=isinstance(
                r.command, CreateProject | ReplaceDesign | ReplaceInputs | Undo
            ),
            current=r.seq == last,
        )
        for r in reversed(records)
    ]


@router.get("/projects/{project_id}/versions/{seq}", response_model=ProjectView)
async def get_version(
    project_id: UUID, seq: int, container: ContainerDep, user: UserDep
) -> ProjectView:
    """Read-only view of the project as it was after version ``seq``."""
    model = await container.projects.version(user.id, project_id, seq)
    return ProjectView(project=model, can_undo=False)


@router.post("/projects/{project_id}/versions/{seq}/restore", response_model=CommandResponse)
async def restore_version(
    project_id: UUID, seq: int, container: ContainerDep, user: UserDep
) -> CommandResponse:
    return _command_response(await container.projects.restore(user.id, project_id, seq))


async def _model(
    container: ContainerDep, owner_id: UUID, project_id: UUID, seq: int | None
) -> ProjectModel:
    if seq is None:
        return await container.projects.get(owner_id, project_id)
    return await container.projects.version(owner_id, project_id, seq)


@router.get(
    "/projects/{project_id}/drawings/{view}.svg",
    response_class=Response,
    responses={200: {"content": {"image/svg+xml": {}}}},
)
async def drawing(
    project_id: UUID, view: str, container: ContainerDep, user: UserDep, seq: int | None = None
) -> Response:
    model = await _model(container, user.id, project_id, seq)
    for d in model.result.drawings:
        if d.view == view:
            return Response(render_svg(d, element_id=f"drawing-{view}"), media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="Unknown view")


@router.get(
    "/projects/{project_id}/document.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def document(
    project_id: UUID, container: ContainerDep, user: UserDep, seq: int | None = None
) -> Response:
    model = await _model(container, user.id, project_id, seq)
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
