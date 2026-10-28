"""Fingerprint of the stage prompts, like ``agent/provenance.py`` for the chat agent.

It covers every stage's instructions and the output schema as the provider receives it. It is
stored with every stage run; ``tests/test_stage_prompts.py`` compares it with
``prompts/stages.lock`` so that no stage prompt change ships without a new STAGE_PROMPT_VERSION
and a changelog entry. ``task prompt:lock`` updates the lock file.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, cast

from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel

from homeworking.modules.pipeline.prompts import STAGE_PROMPT_VERSION
from homeworking.modules.pipeline.stages import build_agents

LOCK_FILE = Path(__file__).parent / "prompts" / "stages.lock"


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


def fingerprint(spec: dict[str, Any]) -> str:
    raw = json.dumps(spec, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


_cache: list[str] = []


async def stage_fingerprint() -> str:
    """Fingerprint of the live stage prompts (computed once per process)."""
    if not _cache:
        _cache.append(fingerprint(await stage_spec()))
    return _cache[0]


def read_lock() -> dict[str, str]:
    return cast(dict[str, str], json.loads(LOCK_FILE.read_text(encoding="utf-8")))


def write_lock(value: str) -> None:
    lock = {"version": STAGE_PROMPT_VERSION, "fingerprint": value}
    LOCK_FILE.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    """``task prompt:lock``: record the stage fingerprint (refuses without a version bump)."""
    import sys

    value = asyncio.run(stage_fingerprint())
    lock = read_lock() if LOCK_FILE.exists() else {}
    if lock.get("fingerprint") == value:
        print(f"stages.lock is up to date ({STAGE_PROMPT_VERSION}, {value})")
        return
    if lock.get("version") == STAGE_PROMPT_VERSION:
        sys.exit(
            f"A stage prompt changed but STAGE_PROMPT_VERSION is still {STAGE_PROMPT_VERSION}: "
            "bump it in modules/pipeline/prompts/__init__.py and add a changelog entry."
        )
    write_lock(value)
    print(f"stages.lock updated: {STAGE_PROMPT_VERSION} -> {value}")


if __name__ == "__main__":
    main()
