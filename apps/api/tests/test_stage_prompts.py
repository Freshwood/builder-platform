"""Stage prompts are versioned like the agent prompt (see test_prompt_lock.py)."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from syrupy.assertion import SnapshotAssertion

from homeworking.modules.pipeline.prompts import STAGE_PROMPT_VERSION
from homeworking.modules.pipeline.provenance import fingerprint, read_lock, stage_spec

CHANGELOG = Path(__file__).parents[3] / "docs" / "ai" / "PROMPT_CHANGELOG.md"
HOW_TO = (
    "A stage prompt changed. Bump STAGE_PROMPT_VERSION (modules/pipeline/prompts), run "
    "`task prompt:lock`, add an entry to docs/ai/PROMPT_CHANGELOG.md and update the snapshot "
    "(`task test -- --snapshot-update`)."
)


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return asyncio.run(stage_spec())


def test_stage_prompts_match_lock(spec: dict[str, Any]) -> None:
    lock = read_lock()
    assert fingerprint(spec) == lock["fingerprint"], HOW_TO
    assert lock["version"] == STAGE_PROMPT_VERSION, HOW_TO


def test_stage_version_is_in_changelog() -> None:
    assert f"## {STAGE_PROMPT_VERSION} " in CHANGELOG.read_text(encoding="utf-8"), HOW_TO


def test_stage_prompt_snapshot(spec: dict[str, Any], snapshot: SnapshotAssertion) -> None:
    assert spec == snapshot
