"""Stage endpoints of the design pipeline (ADR-0010): intake (questions), skeleton and modules."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from homeworking.api.deps import ContainerDep, UserDep
from homeworking.bootstrap import Container
from homeworking.construction_model.assembly import AssemblyDesign
from homeworking.construction_model.pipeline import Question, Skeleton, Spec
from homeworking.modules.conversations.service import RunStatus
from homeworking.modules.identity.service import User
from homeworking.modules.pipeline import runs
from homeworking.modules.pipeline.runs import SpecBlockedError, record_stage
from homeworking.modules.pipeline.stages import (
    ModulesRejectedError,
    SkeletonRejectedError,
    StageFailedError,
    StageUsage,
)

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])
log = logging.getLogger("homeworking.pipeline")

# Body of the 422 when a model call fails (provider error, timeout, unusable output).
MODEL_FAILED_MESSAGE = "Der Modellaufruf ist fehlgeschlagen. Bitte versuche es gleich noch einmal."


class IntakeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec: Spec
    # False after the customer answered: only the remaining questions are computed, no model call.
    extract: bool = True
    # Also ask about finish and experience (details that do not shape the design).
    thorough: bool = False


class IntakeResponse(BaseModel):
    spec: Spec
    questions: list[Question]
    ready: bool
    usage: dict[str, Any]


class SkeletonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec: Spec


class SkeletonResponse(BaseModel):
    skeleton: Skeleton
    usage: dict[str, Any]


class ModulesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec: Spec
    skeleton: Skeleton


class ModulesResponse(BaseModel):
    design: AssemblyDesign
    repairs: int  # repair rounds the engine's checks caused (0 = accepted at the first merge)
    usage: dict[str, Any]


def clean_spec(spec: Spec) -> Spec:
    """The brief with personal data redacted; a topic the safety gate blocks is a 422."""
    try:
        return runs.clean_spec(spec)
    except SpecBlockedError as exc:
        raise HTTPException(422, {"blocked": True, "message": exc.message}) from exc


async def _record(
    container: Container,
    user: User,
    usage: StageUsage,
    *,
    status: RunStatus,
    trace_id: str,
    error: str | None = None,
) -> None:
    await record_stage(
        container.conversations, user.id, usage, status=status, trace_id=trace_id, error=error
    )


async def _fail(
    container: Container,
    user: User,
    usage: StageUsage,
    exc: Exception,
    *,
    trace_id: str,
    record: bool = True,
) -> None:
    """Store a failed stage run. A storage problem must not hide the error the caller reports."""
    if not record:
        return
    try:
        await _record(container, user, usage, status="failed", trace_id=trace_id, error=str(exc))
    except Exception:
        log.exception("pipeline_run_not_stored", extra={"trace_id": trace_id})


async def _model_failed(
    container: Container, user: User, exc: StageFailedError, trace_id: str
) -> HTTPException:
    """The model call of a stage failed: store the run with its usage so far, answer 422."""
    log.warning(
        "pipeline_stage_failed",
        extra={"trace_id": trace_id, "stage": exc.usage.stage},
        exc_info=exc.cause,
    )
    await _fail(container, user, exc.usage, exc, trace_id=trace_id)
    return HTTPException(422, MODEL_FAILED_MESSAGE)


@router.post("/intake")
async def intake(body: IntakeRequest, container: ContainerDep, user: UserDep) -> IntakeResponse:
    trace_id = uuid4().hex
    try:
        result = await container.pipeline.intake(
            clean_spec(body.spec), extract=body.extract, thorough=body.thorough
        )
    except StageFailedError as exc:
        raise await _model_failed(container, user, exc, trace_id) from exc
    if result.usage.requests:  # no model call, no cost, nothing to record
        await _record(container, user, result.usage, status="completed", trace_id=trace_id)
    return IntakeResponse(
        spec=result.spec,
        questions=result.questions,
        ready=result.ready,
        usage=result.usage.as_dict(),
    )


@router.post("/skeleton")
async def skeleton(
    body: SkeletonRequest, container: ContainerDep, user: UserDep
) -> SkeletonResponse:
    spec = clean_spec(body.spec)
    if not container.pipeline.ready(spec):
        raise HTTPException(409, "Für das Gerüst fehlen noch Maße.")
    trace_id = uuid4().hex
    try:
        result = await container.pipeline.skeleton(spec)
    except SkeletonRejectedError as exc:
        await _fail(container, user, exc.usage, exc, trace_id=trace_id)
        raise HTTPException(422, exc.errors) from exc
    except StageFailedError as exc:
        raise await _model_failed(container, user, exc, trace_id) from exc
    await _record(container, user, result.usage, status="completed", trace_id=trace_id)
    return SkeletonResponse(skeleton=result.skeleton, usage=result.usage.as_dict())


@router.post("/modules")
async def modules(body: ModulesRequest, container: ContainerDep, user: UserDep) -> ModulesResponse:
    """Design every module of the skeleton, merge and check them with the engine."""
    spec = clean_spec(body.spec)
    if not container.pipeline.ready(spec):
        raise HTTPException(409, "Für die Module fehlen noch Maße.")
    trace_id = uuid4().hex
    try:
        result = await container.pipeline.modules(spec, body.skeleton)
    except ModulesRejectedError as exc:
        # A skeleton rejected up front cost nothing.
        await _fail(
            container, user, exc.usage, exc, trace_id=trace_id, record=bool(exc.usage.requests)
        )
        raise HTTPException(422, exc.errors) from exc
    except StageFailedError as exc:
        raise await _model_failed(container, user, exc, trace_id) from exc
    await _record(container, user, result.usage, status="completed", trace_id=trace_id)
    return ModulesResponse(
        design=result.design, repairs=len(result.repairs), usage=result.usage.as_dict()
    )
