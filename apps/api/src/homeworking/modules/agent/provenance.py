"""Prompt provenance: a fingerprint of everything that steers the model.

The fingerprint covers the instructions (system prompt and planning overview), every tool
definition as the provider receives it (name, description, argument JSON schema) and the
routing rules. It is stored with every agent run, and ``tests/test_prompt_lock.py`` compares it
with ``prompts/prompt.lock`` so that no prompt change ships without a new PROMPT_VERSION and a
changelog entry. ``task prompt:lock`` updates the lock file.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from calc_engine.engine import Engine
from homeworking.modules.agent.prompts import PROMPT_VERSION
from homeworking.modules.agent.routing import ROUTING_VERSION
from homeworking.modules.agent.tools import AgentDeps, build_agent

LOCK_FILE = Path(__file__).parent / "prompts" / "prompt.lock"


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
        raw = json.dumps(self.canonical(), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


async def prompt_spec(engine: Engine) -> PromptSpec:
    """Capture instructions and tool definitions exactly as a model request would carry them."""
    captured: list[AgentInfo] = []

    def capture(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        captured.append(info)
        return ModelResponse(parts=[TextPart("ok")])

    # No tool is called, so the deps are never used.
    deps = AgentDeps(owner_id=uuid4(), projects=cast(Any, None), project_id=None, trace_id="spec")
    await build_agent(FunctionModel(capture), engine).run("spec", deps=deps)
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


_cache: dict[int, str] = {}


async def prompt_fingerprint(engine: Engine) -> str:
    """Fingerprint of the live prompt (computed once per engine and process)."""
    key = id(engine)
    if key not in _cache:
        _cache[key] = (await prompt_spec(engine)).fingerprint
    return _cache[key]


def read_lock() -> dict[str, str]:
    return cast(dict[str, str], json.loads(LOCK_FILE.read_text(encoding="utf-8")))


def write_lock(fingerprint: str) -> None:
    lock = {"version": PROMPT_VERSION, "fingerprint": fingerprint}
    LOCK_FILE.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    """``task prompt:lock``: record the current fingerprint (refuses without a version bump)."""
    import asyncio
    import sys

    from calc_engine.engine import default_engine

    fingerprint = asyncio.run(prompt_fingerprint(default_engine()))
    lock = read_lock() if LOCK_FILE.exists() else {}
    if lock.get("fingerprint") == fingerprint:
        print(f"prompt.lock is up to date ({PROMPT_VERSION}, {fingerprint})")
        return
    if lock.get("version") == PROMPT_VERSION:
        sys.exit(
            f"The prompt changed but PROMPT_VERSION is still {PROMPT_VERSION}: bump it in "
            "modules/agent/prompts/__init__.py and add an entry to docs/ai/PROMPT_CHANGELOG.md."
        )
    write_lock(fingerprint)
    print(f"prompt.lock updated: {PROMPT_VERSION} -> {fingerprint}")


if __name__ == "__main__":
    main()
