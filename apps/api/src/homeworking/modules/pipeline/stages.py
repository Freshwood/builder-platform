"""Stages 1 and 2 of the design pipeline (ADR-0010): intake and skeleton.

Both stages call a model without tools and with a short prompt; the engine decides everything
that can be decided by rules (which questions are open, what the skeleton must satisfy). A stage
returns its result together with the usage of every model request, because AI results cost money
and every run is stored (see ``api/pipeline.py``).
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model

from calc_engine.pipeline.gaps import apply_updates, is_ready, open_questions
from calc_engine.pipeline.skeleton import check_skeleton, normalize
from construction_model.pipeline import Question, Skeleton, Spec, SpecUpdates
from homeworking.modules.agent.model import Models
from homeworking.modules.pipeline import offline
from homeworking.modules.pipeline.prompts import INTAKE, SKELETON
from homeworking.settings import Settings

# Candidates handed to the intake model (what is still open); the customer sees at most 3.
MAX_OPEN_FOR_MODEL = 6
MAX_QUESTIONS = 3
SKELETON_ATTEMPTS = 2


class IntakeOutput(BaseModel):
    """What the intake model returns: facts read from the text and question wording."""

    model_config = ConfigDict(extra="forbid")

    updates: SpecUpdates = Field(default_factory=SpecUpdates)
    wording: dict[str, str] = Field(default_factory=dict, max_length=MAX_OPEN_FOR_MODEL)


@dataclass
class StageUsage:
    stage: str
    model: str = ""
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    duration_ms: int = 0

    def add(self, model: str, usage: Any) -> None:
        self.model = model
        self.requests += usage.requests
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.cache_read_tokens += usage.cache_read_tokens

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class SkeletonRejectedError(ValueError):
    """The model did not deliver a usable skeleton within its attempts."""

    def __init__(self, errors: list[str], usage: StageUsage) -> None:
        super().__init__("Skeleton rejected: " + "; ".join(errors))
        self.errors = errors
        self.usage = usage


@dataclass
class IntakeResult:
    spec: Spec
    questions: list[Question]
    usage: StageUsage

    @property
    def ready(self) -> bool:
        return is_ready(self.spec)


@dataclass
class SkeletonResult:
    skeleton: Skeleton
    usage: StageUsage
    attempts: list[list[str]] = field(default_factory=list)  # engine problems per failed attempt


def build_agents(
    intake: Model, skeleton: Model
) -> tuple[Agent[None, IntakeOutput], Agent[None, Skeleton]]:
    """The stage agents; also used by ``provenance`` to capture exactly what a request carries."""
    return (
        Agent(intake, output_type=IntakeOutput, instructions=INTAKE, retries=1),
        Agent(skeleton, output_type=Skeleton, instructions=SKELETON, retries=1),
    )


def _spec_line(spec: Spec) -> str:
    return "Steckbrief: " + spec.model_dump_json(exclude_none=True, exclude_defaults=True)


def _word(model_text: str | None, default: str) -> str:
    text = (model_text or "").strip()
    return text if 0 < len(text) <= 200 else default


class Pipeline:
    """Runs the stages. One instance per process; the models come from ``build_models``."""

    def __init__(
        self,
        settings: Settings,
        models: Models,
        species: Mapping[str, str] | None = None,
        *,
        intake_model: Model | None = None,
        skeleton_model: Model | None = None,
    ) -> None:
        offline_mode = settings.llm_mode == "test"
        # Small model for intake; the larger designer model plans the skeleton (ADR-0010).
        self._intake_model: Model = intake_model or (
            offline.intake_model() if offline_mode else models.fast
        )
        self._skeleton_model: Model = skeleton_model or (
            offline.skeleton_model() if offline_mode else models.designer
        )
        self._species = dict(species or {})
        self.intake_agent, self.skeleton_agent = build_agents(
            self._intake_model, self._skeleton_model
        )

    def _woods(self) -> str:
        return "Holzarten: " + ", ".join(self._species)

    @staticmethod
    def ready(spec: Spec) -> bool:
        return is_ready(spec)

    async def intake(
        self, spec: Spec, *, extract: bool = True, thorough: bool = False
    ) -> IntakeResult:
        """Read the text, then ask the few questions the engine still sees open.

        Without open questions no model is called. ``extract=False`` skips the model: used after
        the customer answered, when only the remaining questions need computing."""
        usage = StageUsage("intake")
        started = time.perf_counter()
        pending = open_questions(spec, self._species, limit=MAX_OPEN_FOR_MODEL, thorough=thorough)
        wording: dict[str, str] = {}
        if extract and pending:
            prompt = "\n".join(
                [
                    _spec_line(spec),
                    "Offen: " + ", ".join(q.field for q in pending),
                    self._woods(),
                ]
            )
            result = await self.intake_agent.run(prompt)
            usage.add(self._intake_model.model_name, result.usage)
            spec = apply_updates(spec, result.output.updates)
            wording = result.output.wording
        questions = [
            q.model_copy(update={"text": _word(wording.get(q.field), q.text)})
            for q in open_questions(spec, self._species, limit=MAX_QUESTIONS, thorough=thorough)
        ]
        usage.duration_ms = round((time.perf_counter() - started) * 1000)
        return IntakeResult(spec, questions, usage)

    async def skeleton(self, spec: Spec) -> SkeletonResult:
        """Plan parameters and modules; one repair round with the engine's problems."""
        usage = StageUsage("skeleton")
        started = time.perf_counter()
        prompt = "\n".join([_spec_line(spec), self._woods()])
        failed: list[list[str]] = []
        history: list[ModelMessage] | None = None
        for _ in range(SKELETON_ATTEMPTS):
            result = await self.skeleton_agent.run(prompt, message_history=history)
            usage.add(self._skeleton_model.model_name, result.usage)
            skeleton = normalize(result.output, spec)
            problems = check_skeleton(skeleton, spec)
            if not problems:
                usage.duration_ms = round((time.perf_counter() - started) * 1000)
                return SkeletonResult(skeleton, usage, failed)
            failed.append(problems)
            history = result.all_messages()
            prompt = "Die Engine lehnt das Gerüst ab. Korrigiere genau diese Fehler:\n" + "\n".join(
                f"- {p}" for p in problems
            )
        usage.duration_ms = round((time.perf_counter() - started) * 1000)
        raise SkeletonRejectedError(failed[-1], usage)
