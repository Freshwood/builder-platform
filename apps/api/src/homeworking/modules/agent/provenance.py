"""Prompt provenance: a fingerprint of everything that steers the model.

The fingerprint covers the instructions (system prompt and planning overview), every tool
definition as the provider receives it (name, description, argument JSON schema) and the
routing rules. It is stored with every agent run, and ``tests/test_prompt_lock.py`` compares it
with ``prompts/prompt.lock`` so that no prompt change ships without a new PROMPT_VERSION and a
changelog entry. ``task prompt:lock`` updates the lock file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from homeworking.modules.agent.deps import AgentDeps
from homeworking.modules.agent.prompts import PROMPT_VERSION
from homeworking.modules.agent.routing import ROUTING_VERSION
from homeworking.modules.agent.tools import build_agent
from homeworking.modules.llm.provenance import Once, PromptLock, fingerprint

LOCK = PromptLock(
    path=Path(__file__).parent / "prompts" / "prompt.lock",
    version=PROMPT_VERSION,
    version_name="PROMPT_VERSION",
    what="The prompt",
    bump_hint=(
        "bump it in modules/agent/prompts/__init__.py and add an entry to "
        "docs/ai/PROMPT_CHANGELOG.md."
    ),
)
LOCK_FILE = LOCK.path


@dataclass(frozen=True)
class PromptSpec:
    instructions: str
    tools: list[dict[str, Any]]

    def canonical(self) -> dict[str, Any]:
        return {
            "instructions": self.instructions,
            "tools": self.tools,
            "routing_version": ROUTING_VERSION,
        }

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.canonical())


async def prompt_spec() -> PromptSpec:
    """Capture instructions and tool definitions exactly as a model request would carry them."""
    captured: list[AgentInfo] = []

    def capture(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        captured.append(info)
        return ModelResponse(parts=[TextPart("ok")])

    # No tool is called, so the deps are never used.
    deps = AgentDeps(owner_id=uuid4(), projects=cast(Any, None), project_id=None, trace_id="spec")
    await build_agent(FunctionModel(capture)).run("spec", deps=deps)
    info = captured[0]
    return PromptSpec(
        instructions=info.instructions or "",
        tools=[
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters_json_schema,
            }
            for t in info.function_tools
        ],
    )


async def _compute() -> str:
    return (await prompt_spec()).fingerprint


_live = Once(_compute)


async def prompt_fingerprint() -> str:
    """Fingerprint of the live prompt (computed once per process)."""
    return await _live.get()


def read_lock() -> dict[str, str]:
    return LOCK.read()


def main() -> None:
    """``task prompt:lock``: record the current fingerprint (refuses without a version bump)."""
    import asyncio

    LOCK.record(asyncio.run(prompt_fingerprint()))


if __name__ == "__main__":
    main()
