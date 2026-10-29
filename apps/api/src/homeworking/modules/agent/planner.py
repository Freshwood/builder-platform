"""Adapter that lets the chat agent plan new designs through the staged pipeline (ADR-0010).

The agent only knows the ``DesignPlanner`` protocol; this class owns the pipeline run, the safety
check and the storage of every stage run (cost and provenance, like the chat turn itself).
"""

from __future__ import annotations

import logging
import time
from uuid import UUID, uuid4

from homeworking.calc_engine.pipeline.budget import classify, time_budget_s
from homeworking.construction_model.pipeline import Spec
from homeworking.modules.agent.deps import PlanFailedError, PlannedDesign
from homeworking.modules.conversations.service import ConversationService
from homeworking.modules.pipeline.runs import SpecBlockedError, clean_spec, record_stage
from homeworking.modules.pipeline.stages import (
    DeadlineExceededError,
    ModulesRejectedError,
    Pipeline,
    SkeletonRejectedError,
    StageFailedError,
    StageUsage,
)

log = logging.getLogger("homeworking.pipeline")

# Seconds of the time budget kept for the chat model's closing message after the design.
CHAT_RESERVE_S = 6


class ChatPlanner:
    """``DesignPlanner`` for one chat turn."""

    def __init__(
        self,
        pipeline: Pipeline,
        conversations: ConversationService,
        owner_id: UUID,
        chat_id: str | None,
        user_text: str = "",
        *,
        time_budget: bool = True,
    ) -> None:
        self._pipeline = pipeline
        self._conversations = conversations
        self._owner_id = owner_id
        self._chat_id = chat_id
        self._user_text = user_text
        # The budget runs from the start of the chat turn, so a second plan of the same turn only
        # gets what is left.
        self._started = time.monotonic()
        self._time_budget = time_budget

    async def _record(self, usage: StageUsage, error: str | None) -> None:
        await record_stage(
            self._conversations,
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

    def _budget_s(self, spec: Spec) -> float | None:
        if not self._time_budget:
            return None
        used = time.monotonic() - self._started
        return time_budget_s(spec) - used - CHAT_RESERVE_S

    async def plan(self, spec: Spec) -> PlannedDesign:
        try:
            cleaned = clean_spec(self._with_wording(spec))
        except SpecBlockedError as exc:  # the safety gate refused the brief
            raise PlanFailedError([exc.message]) from exc
        try:
            result = await self._pipeline.design(
                cleaned, on_stage=self._record, budget_s=self._budget_s(cleaned)
            )
        except SkeletonRejectedError as exc:
            raise PlanFailedError(exc.errors) from exc
        except ModulesRejectedError as exc:
            raise PlanFailedError(
                [f"{key}: {text}" for key, texts in exc.errors.items() for text in texts]
            ) from exc
        except (
            StageFailedError
        ) as exc:  # provider errors, timeouts: the chat can still explain them
            log.warning("plan_failed", extra={"stage": exc.usage.stage}, exc_info=exc.cause)
            if isinstance(exc.cause, DeadlineExceededError):
                seconds = time_budget_s(cleaned)
                raise PlanFailedError(
                    [
                        f"Zeitbudget von {seconds} s ({classify(cleaned)}) in der Stufe "
                        f"{exc.usage.stage} aufgebraucht"
                    ]
                ) from exc
            raise PlanFailedError(
                [f"Modellaufruf fehlgeschlagen: {type(exc.cause).__name__}"]
            ) from exc
        except Exception as exc:  # anything else the pipeline raised
            log.exception("plan_failed")
            raise PlanFailedError([f"Modellaufruf fehlgeschlagen: {type(exc).__name__}"]) from exc
        return PlannedDesign(result.design, result.explanation)
