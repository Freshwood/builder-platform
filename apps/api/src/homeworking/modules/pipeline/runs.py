"""What every caller of the pipeline stages shares: the safety gate for a brief and the storage of
a stage run (cost and provenance). Used by the API endpoints and by the chat planner."""

from __future__ import annotations

import logging
from uuid import UUID

from homeworking.construction_model.pipeline import Spec
from homeworking.modules.compliance.redaction import redact
from homeworking.modules.compliance.safety import SAFETY_RULES_VERSION, check_message
from homeworking.modules.conversations.service import AgentRun, ConversationService, RunStatus
from homeworking.modules.pipeline.prompts import STAGE_PROMPT_VERSION
from homeworking.modules.pipeline.provenance import stage_fingerprint
from homeworking.modules.pipeline.stages import StageUsage

log = logging.getLogger("homeworking.pipeline")

# Stage -> model role of the run record (see ADR-0010: small intake and modules, larger skeleton).
_ROLES = {"intake": "fast", "skeleton": "designer", "modules": "fast", "docs": "fast"}


class SpecBlockedError(ValueError):
    """The safety gate refuses the brief (balconies, stairs, electrics, ...)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


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
        raise SpecBlockedError(verdict.response or "")
    return cleaned


async def record_stage(
    conversations: ConversationService,
    owner_id: UUID,
    usage: StageUsage,
    *,
    status: RunStatus,
    trace_id: str,
    error: str | None = None,
    chat_id: str | None = None,
) -> None:
    """Every stage run is stored, also failed ones: AI results cost money."""
    await conversations.record(
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
