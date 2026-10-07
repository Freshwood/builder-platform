"""Every prompt change must be versioned and documented (docs/ai/PROMPT_CHANGELOG.md).

What steers the model is captured exactly as a model request carries it (instructions, tool
definitions, routing version). The snapshot makes every change visible in review; the lock
makes sure it ships with a new PROMPT_VERSION and a changelog entry.
"""

import asyncio
from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from calc_engine.engine import default_engine
from homeworking.modules.agent.prompts import PROMPT_VERSION
from homeworking.modules.agent.provenance import PromptSpec, prompt_spec, read_lock

CHANGELOG = Path(__file__).parents[3] / "docs" / "ai" / "PROMPT_CHANGELOG.md"
HOW_TO = (
    "The prompt changed. Bump PROMPT_VERSION, run `task prompt:lock`, add an entry to "
    "docs/ai/PROMPT_CHANGELOG.md and update the snapshot (`task test -- --snapshot-update`)."
)


@pytest.fixture(scope="module")
def spec() -> PromptSpec:
    return asyncio.run(prompt_spec(default_engine()))


def test_prompt_matches_lock(spec: PromptSpec) -> None:
    lock = read_lock()
    assert spec.fingerprint == lock["fingerprint"], HOW_TO
    assert lock["version"] == PROMPT_VERSION, HOW_TO


def test_prompt_version_is_in_changelog() -> None:
    assert f"## {PROMPT_VERSION} " in CHANGELOG.read_text(encoding="utf-8"), HOW_TO


def test_prompt_snapshot(spec: PromptSpec, snapshot: SnapshotAssertion) -> None:
    assert spec.canonical() == snapshot
