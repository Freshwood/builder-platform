"""Adapter that lets the chat agent plan new designs through the staged pipeline (ADR-0010).

The agent only knows the ``DesignPlanner`` protocol; this API-layer class owns the pipeline, the
safety check and the storage of every stage run (cost and provenance, like the chat turn itself).
"""

from __future__ import annotations

import logging
from uuid import UUID, uuid4

from fastapi import HTTPException

from construction_model.pipeline import Spec
from homeworking.api.pipeline import clean_spec, record_stage
from homeworking.bootstrap import Container
from homeworking.modules.agent.tools import PlanFailedError, PlannedDesign
from homeworking.modules.pipeline.stages import (
    ModulesRejectedError,
    SkeletonRejectedError,
    StageUsage,
)

log = logging.getLogger("homeworking.pipeline")


class ChatPlanner:
    """``DesignPlanner`` for one chat turn."""

    def __init__(
        self, container: Container, owner_id: UUID, chat_id: str | None, user_text: str = ""
    ) -> None:
        self._container = container
        self._owner_id = owner_id
        self._chat_id = chat_id
        self._user_text = user_text

    async def _record(self, usage: StageUsage, error: str | None) -> None:
        await record_stage(
            self._container,
            self._owner_id,
            usage,
            status="failed" if error else "completed",
            trace_id=uuid4().hex,
            error=error,
            chat_id=self._chat_id,
        )

    def _with_wording(self, spec: Spec) -> Spec:
        """Add the customer's own words: the chat model's brief tends to drop wishes such as the
        material or the number of shelves (live run, regression briefs)."""
        text = self._user_text.strip()
        if not text or text in spec.description:
            return spec
        merged = f"{spec.description}\nWortlaut des Kunden: {text}"
        return spec.model_copy(update={"description": merged[:2000]})

    async def plan(self, spec: Spec) -> PlannedDesign:
        try:
            cleaned = clean_spec(self._with_wording(spec))
        except HTTPException as exc:  # the safety gate refused the brief
            detail = exc.detail
            message = detail.get("message") if isinstance(detail, dict) else None
            raise PlanFailedError([str(message or detail)]) from exc
        try:
            result = await self._container.pipeline.design(cleaned, on_stage=self._record)
        except SkeletonRejectedError as exc:
            raise PlanFailedError(exc.errors) from exc
        except ModulesRejectedError as exc:
            raise PlanFailedError(
                [f"{key}: {text}" for key, texts in exc.errors.items() for text in texts]
            ) from exc
        except Exception as exc:  # provider errors, timeouts: the chat can still explain them
            log.exception("plan_failed")
            raise PlanFailedError([f"Modellaufruf fehlgeschlagen: {type(exc).__name__}"]) from exc
        return PlannedDesign(result.design, result.explanation)
