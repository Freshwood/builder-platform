"""Fingerprint of the stage prompts, like ``agent/provenance.py`` for the chat agent.

It covers every stage's instructions and the output schema as the provider receives it. It is
stored with every stage run; ``tests/test_stage_prompts.py`` compares it with
``prompts/stages.lock`` so that no stage prompt change ships without a new STAGE_PROMPT_VERSION
and a changelog entry. ``task prompt:lock`` updates the lock file.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel

from homeworking.modules.llm.provenance import Once, PromptLock, fingerprint
from homeworking.modules.pipeline.prompts import STAGE_PROMPT_VERSION
from homeworking.modules.pipeline.stages import build_agents

LOCK = PromptLock(
    path=Path(__file__).parent / "prompts" / "stages.lock",
    version=STAGE_PROMPT_VERSION,
    version_name="STAGE_PROMPT_VERSION",
    what="A stage prompt",
    bump_hint="bump it in modules/pipeline/prompts/__init__.py and add a changelog entry.",
)
LOCK_FILE = LOCK.path


class _Captured(Exception):  # noqa: N818 - control flow, not an error
    def __init__(self, info: AgentInfo) -> None:
        super().__init__("captured")
        self.info = info


def _capture(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    raise _Captured(info)


async def stage_spec() -> dict[str, Any]:
    """Instructions and output schema of every stage exactly as a model request carries them."""
    model = FunctionModel(_capture)
    agents = dict(
        zip(
            ("intake", "skeleton", "modules", "docs"),
            build_agents(model, model, model, model),
            strict=True,
        )
    )
    spec: dict[str, Any] = {}
    for name, agent in agents.items():
        try:
            await agent.run("spec")
        except _Captured as captured:
            info = captured.info
            spec[name] = {
                "instructions": info.instructions or "",
                "output": [t.parameters_json_schema for t in info.output_tools],
            }
    return spec


async def _compute() -> str:
    return fingerprint(await stage_spec())


_live = Once(_compute)


async def stage_fingerprint() -> str:
    """Fingerprint of the live stage prompts (computed once per process)."""
    return await _live.get()


def read_lock() -> dict[str, str]:
    return LOCK.read()


def main() -> None:
    """``task prompt:lock``: record the stage fingerprint (refuses without a version bump)."""
    LOCK.record(asyncio.run(stage_fingerprint()))


if __name__ == "__main__":
    main()
