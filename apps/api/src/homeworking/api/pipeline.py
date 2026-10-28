"""Stage endpoints of the design pipeline (ADR-0010): intake (questions), skeleton and modules."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from construction_model.assembly import AssemblyDesign
from construction_model.pipeline import Question, Skeleton, Spec
from homeworking.api.deps import ContainerDep, UserDep
from homeworking.bootstrap import Container
from homeworking.modules.compliance.redaction import redact
from homeworking.modules.compliance.safety import SAFETY_RULES_VERSION, check_message
from homeworking.modules.conversations.service import AgentRun, RunStatus
from homeworking.modules.pipeline.prompts import STAGE_PROMPT_VERSION
from homeworking.modules.pipeline.provenance import stage_fingerprint
from homeworking.modules.pipeline.stages import (
    ModulesRejectedError,
    SkeletonRejectedError,
    StageUsage,
)

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])
log = logging.getLogger("homeworking.pipeline")

# Stage -> model role of the run record (see ADR-0010: small intake and modules, larger skeleton).
_ROLES = {"intake": "fast", "skeleton": "designer", "modules": "fast", "docs": "fast"}


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
    """Redact personal data in every free-text field; refuse topics the safety gate blocks."""
    cleaned = spec.model_copy(
        update={
            "description": redact(spec.description),
            "usage": redact(spec.usage) if spec.usage else None,
            "details": {k: redact(v) for k, v in spec.details.items()},
        }
    )
    text = " ".join([cleaned.description, cleaned.usage or "", *cleaned.details.values()])
    verdict = check_message(text)
    if verdict.blocked:
        raise HTTPException(422, {"blocked": True, "message": verdict.response})
    return cleaned


async def record_stage(
    container: Container,
    owner_id: UUID,
    usage: StageUsage,
    *,
    status: RunStatus,
    trace_id: str,
    error: str | None = None,
    chat_id: str | None = None,
) -> None:
    """Every stage run is stored, also failed ones: AI results cost money."""
    await container.conversations.record(
        AgentRun(
            trace_id=trace_id,
            owner_id=owner_id,
            chat_id=chat_id,
            project_id=None,
            status=status,
            model=usage.model,
            prompt_version=STAGE_PROMPT_VERSION,
            ui_messages=[],
            usage=usage.as_dict(),
            error=error,
            prompt_fingerprint=await stage_fingerprint(),
            safety_rules_version=SAFETY_RULES_VERSION,
            model_role=_ROLES[usage.stage],
            routing_reason=f"stage:{usage.stage}",
            duration_ms=usage.duration_ms,
        )
    )
    log.info("pipeline_stage", extra={"trace_id": trace_id, **usage.as_dict()})


async def _record(
    container: ContainerDep,
    user: UserDep,
    usage: StageUsage,
    *,
    status: RunStatus,
    trace_id: str,
    error: str | None = None,
) -> None:
    await record_stage(container, user.id, usage, status=status, trace_id=trace_id, error=error)


@router.post("/intake")
async def intake(body: IntakeRequest, container: ContainerDep, user: UserDep) -> IntakeResponse:
    result = await container.pipeline.intake(
        clean_spec(body.spec), extract=body.extract, thorough=body.thorough
    )
    if result.usage.requests:  # no model call, no cost, nothing to record
        await _record(container, user, result.usage, status="completed", trace_id=uuid4().hex)
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
        await _record(
            container, user, exc.usage, status="failed", trace_id=trace_id, error=str(exc)
        )
        raise HTTPException(422, exc.errors) from exc
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
        if exc.usage.requests:  # a skeleton rejected up front cost nothing
            await _record(
                container, user, exc.usage, status="failed", trace_id=trace_id, error=str(exc)
            )
        raise HTTPException(422, exc.errors) from exc
    await _record(container, user, result.usage, status="completed", trace_id=trace_id)
    return ModulesResponse(
        design=result.design, repairs=len(result.repairs), usage=result.usage.as_dict()
    )
