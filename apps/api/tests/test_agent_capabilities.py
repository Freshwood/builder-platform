"""The agent's observers must never break a run, and what they store must stay JSON."""

import json
from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from homeworking.modules.agent.deps import RAW_ARGS_MAX_CHARS, AgentDeps, stored_raw_args
from homeworking.modules.agent.tools import build_agent


def _answer(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[TextPart("Fertig.")])


def _deps() -> AgentDeps:
    return AgentDeps(
        owner_id=uuid4(),
        projects=None,  # type: ignore[arg-type]
        project_id=None,
        trace_id="t",
    )


async def test_a_failing_request_recorder_does_not_break_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def broken(*_args: object, **_kwargs: object) -> dict[str, Any]:
        raise RuntimeError("cannot describe the request")

    monkeypatch.setattr("homeworking.modules.agent.capabilities.request_shape", broken)
    deps = _deps()
    result = await build_agent(FunctionModel(_answer)).run("Hallo", deps=deps)
    assert result.output == "Fertig."
    assert deps.request_count == 1
    assert deps.last_request_shape is None  # nothing recorded, nothing broken
    assert deps.last_request_error is None


async def test_the_request_shape_is_recorded_when_nothing_fails() -> None:
    deps = _deps()
    await build_agent(FunctionModel(_answer)).run("Hallo", deps=deps)
    assert deps.last_request_shape is not None
    assert deps.request_open is None


def test_stored_raw_args_keep_text_and_objects_json_safe() -> None:
    assert stored_raw_args(None) is None
    assert stored_raw_args('{"a": ') == '{"a": '  # broken JSON text is kept as sent
    stored = stored_raw_args({"design": {"parts": [1, 2]}, "odd": {1, 2}})
    assert isinstance(stored, dict)
    assert stored["design"] == {"parts": [1, 2]}
    assert isinstance(stored["odd"], str)  # not JSON: stringified, never an exception
    json.dumps(stored)


def test_stored_raw_args_are_bounded() -> None:
    long_text = "x" * (RAW_ARGS_MAX_CHARS + 10)
    text = stored_raw_args(long_text)
    assert isinstance(text, str)
    assert text.endswith(f"[truncated, {len(long_text)} chars in total]")
    huge = stored_raw_args({"design": long_text})
    assert isinstance(huge, str)
    assert "truncated" in huge
