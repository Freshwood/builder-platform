"""A failed model request leaves its shape (no text) in the run record (``usage.failed_request``).

Everything is offline: scripted ``FunctionModel`` runs, an ``ModelHTTPError`` as the provider's
400 and an OpenAI model that is only used to map messages (no request is ever sent).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import (
    InstructionPart,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestContext, ModelRequestParameters
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from sqlalchemy import select

from homeworking.bootstrap import build_container
from homeworking.db.schema import AgentRunRow
from homeworking.main import create_app
from homeworking.modules.agent import request_shape as shape
from homeworking.modules.agent.model import Models
from homeworking.modules.agent.tools import AgentDeps, build_agent
from homeworking.settings import Settings

SECRET = "SENTINEL-GEHEIM-7731"
PROVIDER_BODY = {
    "error": {
        "message": "Missing required parameter: 'messages[6].content'.",
        "type": "invalid_request_error",
    }
}


class MappingFunctionModel(FunctionModel):
    """A ``FunctionModel`` that maps messages like the OpenAI chat model (offline)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._mapper = OpenAIChatModel("m", provider=OpenAIProvider(api_key="unused"))

    async def _map_messages(
        self, messages: Sequence[ModelMessage], params: ModelRequestParameters, **kwargs: Any
    ) -> list[Any]:
        return await self._mapper._map_messages(messages, params, **kwargs)


class BrokenMapper(FunctionModel):
    async def _map_messages(self, *args: Any, **kwargs: Any) -> list[Any]:
        raise RuntimeError("internal changed")


@dataclass
class Script:
    """Tool calls the scripted model makes, one per request, then ``end``."""

    calls: list[str]
    end: str  # "answer" or "http_400"

    def step(self, messages: list[ModelMessage]) -> ModelResponse:
        sent = sum(isinstance(m, ModelResponse) for m in messages)
        if sent < len(self.calls):
            return ModelResponse(
                parts=[ToolCallPart(self.calls[sent], {}, tool_call_id=f"call_{sent}_abcdef123456")]
            )
        if self.end == "http_400":
            raise ModelHTTPError(400, "upstage/solar-pro-4", PROVIDER_BODY)
        return ModelResponse(parts=[TextPart("Fertig.")])


def scripted(script: Script, model_class: type[FunctionModel] = MappingFunctionModel) -> Any:
    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        return script.step(messages)

    async def stream(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[Any]:
        response = script.step(messages)
        part = response.parts[0]
        if isinstance(part, ToolCallPart):
            yield {
                0: DeltaToolCall(
                    name=part.tool_name, json_args="{}", tool_call_id=part.tool_call_id
                )
            }
        else:
            yield "Fertig."

    return model_class(respond, stream_function=stream)


def add_tools(agent: Agent[AgentDeps, str]) -> None:
    """Tools with a known result: a secret text, nothing at all (the empty tool return), a number."""

    @agent.tool_plain
    def reveal() -> str:
        return f"vertraulich {SECRET}"

    @agent.tool_plain
    def nothing() -> None:
        return None

    @agent.tool_plain
    def number() -> int:
        return 7


CALLS = ["reveal", "nothing", "number"]


@asynccontextmanager
async def app_with(settings: Settings, script: Script) -> AsyncIterator[Any]:
    app = create_app(settings, create_schema=True)
    async with app.router.lifespan_context(app):
        container = app.state.container
        model = scripted(script)
        container.models = Models(designer=model, fast=model)
        container.agent = build_agent(model, container.engine)
        add_tools(container.agent)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield container, client


@dataclass
class StoredRun:
    status: str
    model_messages: Any
    usage: dict[str, Any]
    ui_messages: Any


async def chat(client: httpx.AsyncClient, text: str) -> str:
    body = {
        "trigger": "submit-message",
        "id": "c1",
        "messages": [{"id": "m1", "role": "user", "parts": [{"type": "text", "text": text}]}],
    }
    response = await client.post("/api/chat", json=body)
    assert response.status_code == 200, response.text
    return response.text


async def last_run(container: Any) -> StoredRun:
    async with container.sessions() as session:
        rows = await session.scalars(select(AgentRunRow).order_by(AgentRunRow.created_at.desc()))
        row = rows.first()
    assert row is not None
    assert row.usage is not None
    return StoredRun(row.status, row.model_messages, row.usage, row.ui_messages)


def context(
    messages: list[ModelMessage], model: Any | None = None, instructions: str | None = "Regeln"
) -> ModelRequestContext:
    parts = [InstructionPart(content=instructions)] if instructions else []
    return ModelRequestContext(
        model=model or MappingFunctionModel(lambda m, i: ModelResponse(parts=[])),
        messages=messages,
        model_settings=None,
        model_request_parameters=ModelRequestParameters(instruction_parts=parts),
    )


def request(*parts: Any) -> ModelRequest:
    return ModelRequest(parts=list(parts))


def call(name: str, call_id: str) -> ToolCallPart:
    return ToolCallPart(name, {}, tool_call_id=call_id)


# --------------------------------------------------------------------------------------------
# The stored record of a failed run
# --------------------------------------------------------------------------------------------


async def test_failed_run_stores_the_shape_of_the_failing_request(settings: Settings) -> None:
    async with app_with(settings, Script(CALLS, "http_400")) as (container, client):
        await chat(client, f"Bitte ein Regal. {SECRET}")
        run = await last_run(container)

    assert run.status == "failed"
    assert run.model_messages is None
    record = run.usage["failed_request"]
    assert record["request_number"] == 4
    assert record["model_call_failed"] is True
    assert record["error_class"] == "ModelHTTPError"
    assert record["status_code"] == 400
    assert record["shape_version"] == shape.SHAPE_VERSION
    assert record["pydantic_ai"]
    # Three finished rounds: user prompt, then (call, return) three times.
    assert record["messages_total"] == 7
    assert [m["kind"] for m in record["messages"]] == ["request", "response"] * 3 + ["request"]
    first = record["messages"][0]["parts"][0]
    assert first["kind"] == "user-prompt"
    assert first["chars"] > len(SECRET)
    returned = [p for m in record["messages"] for p in m["parts"] if p["kind"] == "tool-return"]
    assert [p["tool"] for p in returned] == CALLS
    assert [bool(p.get("empty")) for p in returned] == [False, True, False]
    assert returned[0]["id"].startswith("…")
    assert len(returned[0]["id"]) <= 10

    provider = record["provider"]
    assert provider["available"] is True
    # instructions + user + 3 x (assistant, tool)
    assert provider["total"] == 8
    assert provider["messages"][0]["role"] == "system"
    # The tool that returned nothing is provider message 5, pydantic-ai message 4.
    assert provider["suspicious"] == [5]
    assert provider["suspicious_source"] == [{"provider": 5, "message": 4}]
    assert record["messages"][4]["parts"][0]["tool"] == "nothing"
    assert len(json.dumps(record)) < 20_000


async def test_stored_failed_request_holds_no_text(settings: Settings) -> None:
    async with app_with(settings, Script(CALLS, "http_400")) as (container, client):
        await chat(client, f"Bitte ein Regal. {SECRET}")
        run = await last_run(container)

    stored = json.dumps(run.usage)
    assert "failed_request" in stored
    assert SECRET not in stored  # neither the user text nor the tool output
    assert "vertraulich" not in stored
    assert "Bitte ein Regal" not in stored
    # The secret did reach the model (it is in the stored UI message), so the check is not void.
    assert SECRET in json.dumps(run.ui_messages)


async def test_successful_run_stores_no_shape(settings: Settings) -> None:
    async with app_with(settings, Script(CALLS, "answer")) as (container, client):
        await chat(client, "Bitte ein Regal.")
        run = await last_run(container)

    assert run.status == "completed"
    assert "failed_request" not in run.usage
    assert run.usage["requests"] == 4


async def test_shape_is_kept_per_run_without_growth(settings: Settings) -> None:
    container = build_container(settings)
    await container.create_schema()
    try:
        owner = (await container.identity.create_guest()).id
        agent = build_agent(scripted(Script(CALLS, "answer")), container.engine)
        add_tools(agent)
        deps = AgentDeps(owner_id=owner, projects=container.projects, project_id=None, trace_id="t")
        await agent.run("Ein Regal", deps=deps)
    finally:
        await container.close()
    # Only the latest request is kept; the run made four.
    assert deps.request_count == 4
    assert deps.last_request_shape is not None
    assert deps.last_request_shape["request_number"] == 4
    assert deps.last_request_error is None


async def test_provider_error_other_than_http_still_records_the_class(settings: Settings) -> None:
    def broken(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise TimeoutError("zu langsam " + SECRET)

    container = build_container(settings)
    await container.create_schema()
    try:
        owner = (await container.identity.create_guest()).id
        agent = build_agent(FunctionModel(broken), container.engine)
        deps = AgentDeps(owner_id=owner, projects=container.projects, project_id=None, trace_id="t")
        with pytest.raises(TimeoutError):
            await agent.run("Ein Regal", deps=deps)
    finally:
        await container.close()
    record = shape.failed_request(deps.last_request_shape, deps.last_request_error)
    assert record is not None
    assert (record["error_class"], record["status_code"]) == ("TimeoutError", None)
    assert record["request_number"] == 1
    assert record["provider"] == {"available": False, "reason": "no_mapper"}
    assert SECRET not in json.dumps(record)


async def test_failing_mapper_never_breaks_the_run(settings: Settings) -> None:
    container = build_container(settings)
    await container.create_schema()
    try:
        owner = (await container.identity.create_guest()).id
        model = scripted(Script(CALLS, "answer"), BrokenMapper)
        agent = build_agent(model, container.engine)
        add_tools(agent)
        deps = AgentDeps(owner_id=owner, projects=container.projects, project_id=None, trace_id="t")
        result = await agent.run("Ein Regal", deps=deps)
    finally:
        await container.close()
    assert result.output == "Fertig."
    assert deps.last_request_shape is not None
    assert deps.last_request_shape["provider"] == {"available": False, "reason": "RuntimeError"}


def test_failed_request_without_a_shape_is_none() -> None:
    assert shape.failed_request(None, {"request_number": 1, "error_class": "X"}) is None


def test_failure_outside_the_model_call_is_marked() -> None:
    last = {"request_number": 2, "messages": []}
    record = shape.failed_request(last, None)
    assert record is not None
    assert record["model_call_failed"] is False
    assert record["error_class"] is None


# --------------------------------------------------------------------------------------------
# The shape function on hand-built messages, one pattern at a time
# --------------------------------------------------------------------------------------------


async def provider_view(messages: list[ModelMessage]) -> dict[str, Any]:
    record = await shape.request_shape(context(messages), 4)
    view: dict[str, Any] = record["provider"]
    assert view["available"] is True
    return view


async def test_empty_tool_return_is_suspicious() -> None:
    messages: list[ModelMessage] = [
        request(UserPromptPart("Hallo")),
        ModelResponse(parts=[call("nothing", "call_1")]),
        request(ToolReturnPart("nothing", "", tool_call_id="call_1")),
    ]
    record = await shape.request_shape(context(messages), 2)
    assert record["messages"][2]["parts"][0] == {
        "kind": "tool-return",
        "tool": "nothing",
        "id": "call_1",
        "chars": 0,
        "empty": True,
    }
    view = record["provider"]
    assert [m["role"] for m in view["messages"]] == ["system", "user", "assistant", "tool"]
    assert view["suspicious"] == [3]
    assert view["suspicious_source"] == [{"provider": 3, "message": 2}]


async def test_none_tool_return_is_suspicious_too() -> None:
    messages: list[ModelMessage] = [
        request(UserPromptPart("Hallo")),
        ModelResponse(parts=[call("nothing", "call_1")]),
        request(ToolReturnPart("nothing", None, tool_call_id="call_1")),
    ]
    assert (await provider_view(messages))["suspicious"] == [3]


async def test_assistant_without_content_and_tool_calls_is_suspicious() -> None:
    messages: list[ModelMessage] = [
        request(UserPromptPart("Hallo")),
        ModelResponse(parts=[TextPart("")]),
        request(UserPromptPart("Weiter")),
    ]
    view = await provider_view(messages)
    assert view["suspicious"] == [2]
    assert view["messages"][2] | {"i": 2} == {
        "i": 2,
        "role": "assistant",
        "has_content": False,
        "chars": 0,
        "tool_calls": 0,
        "tool_call_id": False,
    }


async def test_assistant_with_only_tool_calls_is_not_suspicious() -> None:
    messages: list[ModelMessage] = [
        request(UserPromptPart("Hallo")),
        ModelResponse(parts=[call("a", "call_1"), call("b", "call_2")]),
        request(
            ToolReturnPart("a", "x", tool_call_id="call_1"),
            ToolReturnPart("b", "y", tool_call_id="call_2"),
        ),
    ]
    view = await provider_view(messages)
    assert view["suspicious"] == []
    assert view["messages"][2]["tool_calls"] == 2
    assert view["messages"][2]["has_content"] is False
    # One request with two tool returns becomes two provider messages.
    assert [m["role"] for m in view["messages"]] == ["system", "user", "assistant", "tool", "tool"]


async def test_thinking_only_response_is_content() -> None:
    messages: list[ModelMessage] = [
        request(UserPromptPart("Hallo")),
        ModelResponse(parts=[ThinkingPart("hmm")]),
        request(UserPromptPart("Weiter")),
    ]
    view = await provider_view(messages)
    assert view["suspicious"] == []
    assert view["messages"][2]["has_content"] is True


async def test_empty_response_vanishes_and_shifts_the_provider_indices() -> None:
    messages: list[ModelMessage] = [
        request(UserPromptPart("Hallo")),
        ModelResponse(parts=[]),
        request(ToolReturnPart("x", "", tool_call_id="c"), UserPromptPart("Weiter")),
    ]
    record = await shape.request_shape(context(messages), 3)
    assert record["messages"][1] == {"i": 1, "kind": "response", "parts": [], "empty": True}
    view = record["provider"]
    # system, user, tool (empty), user: the empty response left no message.
    assert [m["role"] for m in view["messages"]] == ["system", "user", "tool", "user"]
    assert view["suspicious"] == [2]
    assert view["suspicious_source"] == [{"provider": 2, "message": 2}]


async def test_retry_prompt_with_tool_name_maps_to_a_tool_message() -> None:
    messages: list[ModelMessage] = [
        request(UserPromptPart("Hallo")),
        ModelResponse(parts=[call("a", "call_1")]),
        request(RetryPromptPart("Argument ungültig", tool_name="a", tool_call_id="call_1")),
    ]
    record = await shape.request_shape(context(messages), 3)
    retry = record["messages"][2]["parts"][0]
    assert (retry["kind"], retry["tool"]) == ("retry-prompt", "a")
    assert retry["chars"] > 0
    assert record["provider"]["suspicious"] == []


async def test_whitespace_only_text_is_flagged_empty_in_the_shape() -> None:
    messages: list[ModelMessage] = [
        request(UserPromptPart("Hallo")),
        ModelResponse(parts=[TextPart("  \n")]),
        request(UserPromptPart("Weiter")),
    ]
    record = await shape.request_shape(context(messages), 2)
    assert record["messages"][1]["parts"][0]["empty"] is True
    assert record["messages"][1]["parts"][0]["chars"] == 3
    assert "empty" not in record["messages"][0]["parts"][0]


def test_mapped_shapes_flags_every_pattern() -> None:
    mapped = [
        {"role": "system", "content": "regeln"},  # 0 fine
        {"role": "user", "content": "hallo"},  # 1 fine
        {"role": "assistant", "content": None, "tool_calls": [{"id": "a"}]},  # 2 valid
        {"role": "tool", "tool_call_id": "a", "content": ""},  # 3 empty tool message
        {"role": "assistant", "content": None},  # 4 neither content nor tool calls
        {"role": "assistant", "content": ""},  # 5 same, empty string
        {"role": "tool", "tool_call_id": "b", "content": None},  # 6 tool without content
        {"role": "user", "content": [{"type": "text", "text": "x"}]},  # 7 fine (parts)
        {"role": "user", "content": []},  # 8 no parts
        {"role": "assistant", "content": "ok", "tool_calls": []},  # 9 fine
    ]
    entries, suspicious = shape.mapped_shapes(mapped)
    assert suspicious == [3, 4, 5, 6, 8]
    assert entries[2]["tool_calls"] == 1
    assert entries[2]["has_content"] is False
    assert entries[3]["tool_call_id"] is True
    assert entries[7]["chars"] == 1


async def test_only_the_last_messages_are_kept_and_the_record_stays_small() -> None:
    messages: list[ModelMessage] = [request(UserPromptPart("Hallo"))]
    for n in range(60):
        messages.append(
            ModelResponse(parts=[call("tool_mit_langem_namen", f"call_{n}_" + "x" * 30)])
        )
        messages.append(
            request(
                ToolReturnPart(
                    "tool_mit_langem_namen", "ergebnis" * 10, tool_call_id=f"call_{n}_" + "x" * 30
                )
            )
        )
    record = await shape.request_shape(context(messages), 61)
    assert record["messages_total"] == 121
    assert record["messages_omitted"] == 121 - shape.KEEP_MESSAGES
    assert len(record["messages"]) == shape.KEEP_MESSAGES
    assert record["messages"][-1]["i"] == 120  # absolute indices survive
    assert record["provider"]["total"] == 122
    assert len(record["provider"]["messages"]) == shape.KEEP_MESSAGES
    assert record["provider"]["messages"][-1]["i"] == 121
    assert len(json.dumps(record)) < 20_000


async def test_many_parallel_calls_are_capped() -> None:
    calls = [call("a", f"call_{n}") for n in range(30)]
    record = await shape.request_shape(
        context([request(UserPromptPart("x")), ModelResponse(parts=calls)]), 2
    )
    entry = record["messages"][1]
    assert len(entry["parts"]) == shape.MAX_PARTS
    assert entry["more_parts"] == 30 - shape.MAX_PARTS


def test_error_info_reads_status_from_groups_and_never_the_text() -> None:
    error = ModelHTTPError(429, "m", {"error": SECRET})
    assert shape.error_info(error) == {"error_class": "ModelHTTPError", "status_code": 429}
    group = ExceptionGroup("alle Modelle fehlgeschlagen", [RuntimeError("x"), error])
    assert shape.error_info(group) == {"error_class": "ExceptionGroup", "status_code": 429}
    assert SECRET not in json.dumps(shape.error_info(error))
