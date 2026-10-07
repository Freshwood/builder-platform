"""Agent chat endpoint streaming the Vercel AI SDK UI message protocol."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import anyio
from fastapi import APIRouter, Request, Response
from pydantic import TypeAdapter
from pydantic_ai import Agent, AgentRunResult
from pydantic_ai.models import Model
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import TextUIPart, UIMessage
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk, ErrorChunk
from pydantic_ai.usage import RunUsage, UsageLimits

from homeworking.api.deps import ContainerDep, UserDep
from homeworking.modules.agent.offline import fixed_text_model
from homeworking.modules.agent.prompts import PROMPT_VERSION
from homeworking.modules.agent.provenance import prompt_fingerprint
from homeworking.modules.agent.routing import route
from homeworking.modules.agent.tools import AgentDeps
from homeworking.modules.compliance.redaction import redact
from homeworking.modules.compliance.safety import SAFETY_RULES_VERSION, check_message
from homeworking.modules.conversations.service import AgentRun, RunStatus

router = APIRouter(prefix="/api", tags=["agent"])
log = logging.getLogger("homeworking.agent")

ABORTED_TEXT = "Dieser Durchlauf wurde abgebrochen, es wurde nichts geändert."
_usage_adapter: TypeAdapter[RunUsage] = TypeAdapter(RunUsage)


def _dump(messages: list[UIMessage]) -> list[dict[str, Any]]:
    return [m.model_dump(mode="json", by_alias=True, exclude_none=True) for m in messages]


def _turn_messages(
    run_input: Any, result: AgentRunResult[Any] | None, status: RunStatus
) -> list[dict[str, Any]]:
    """UI messages of this turn: the user's message and what the assistant answered."""
    users = [m for m in run_input.messages if m.role == "user"]
    asked = _dump(users[-1:])
    if result is None:
        aborted = {
            "id": uuid4().hex,
            "role": "assistant",
            "parts": [{"type": "text", "text": ABORTED_TEXT}],
            "metadata": {"status": status},
        }
        return [*asked, aborted]
    answer = [
        m
        for m in _dump(VercelAIAdapter.dump_messages(result.new_messages(), sdk_version=7))
        if m["role"] == "assistant"
    ]
    if not answer:
        return asked
    # One model response per step; the chat shows the whole turn as a single message.
    merged = {**answer[0], "parts": [p for m in answer for p in m["parts"]]}
    return [*asked, merged]


def _usage(result: AgentRunResult[Any] | None, requests: list[dict[str, Any]]) -> dict[str, Any]:
    """Run usage plus a per-request breakdown; summed from the requests if the run failed."""
    if result is not None:
        usage: dict[str, Any] = _usage_adapter.dump_python(result.usage, mode="json")
    else:
        usage = {
            "requests": len(requests),
            **{
                key: sum(r[key] or 0 for r in requests)
                for key in ("input_tokens", "output_tokens", "cache_read_tokens")
            },
        }
    return {**usage, "per_request": requests}


def _project_id(body: dict[str, Any]) -> UUID | None:
    raw = body.get("projectId") or body.get("project_id")
    try:
        return UUID(str(raw)) if raw else None
    except ValueError:
        return None


def _redact_user_messages(run_input: Any) -> str:
    """Redact personal data in user text parts in place; return the last user text."""
    last_text = ""
    for message in run_input.messages:
        if message.role != "user":
            continue
        texts: list[str] = []
        for i, part in enumerate(message.parts):
            if isinstance(part, TextUIPart):
                message.parts[i] = part.model_copy(update={"text": redact(part.text)})
                texts.append(message.parts[i].text)
        last_text = " ".join(texts)
    return last_text


@router.post("/chat", response_class=Response)
async def chat(request: Request, container: ContainerDep, user: UserDep) -> Response:
    body_bytes = await request.body()
    body = json.loads(body_bytes or b"{}")
    run_input = VercelAIAdapter.build_run_input(body_bytes)

    project_id = _project_id(body)
    if project_id is not None:
        try:
            await container.projects.get(user.id, project_id)
        except LookupError:
            project_id = None
    chat_id = str(body.get("id") or "")[:128] or None

    history = await container.conversations.history(user.id, chat_id=chat_id, project_id=project_id)
    if history:
        # Stored runs are the trusted history; of the client's messages only the new one counts
        # (older clients still send the whole chat, which would duplicate it).
        run_input.messages = run_input.messages[-1:]
    last_text = _redact_user_messages(run_input)

    trace_id = uuid4().hex
    verdict = check_message(last_text)
    agent: Agent[AgentDeps, str] = container.agent
    routed = route(last_text, has_project=project_id is not None)
    model: Model | None = container.models.for_role(routed.role)
    model_name = model.model_name if model is not None else ""
    if verdict.blocked and verdict.response:
        agent = Agent(fixed_text_model(verdict.response), deps_type=AgentDeps)
        model, model_name = None, "safety"
    fingerprint = await prompt_fingerprint(container.engine)

    log.info(
        "agent_turn",
        extra={
            "trace_id": trace_id,
            "model": model_name,
            "model_role": routed.role,
            "routing_reason": routed.reason,
            "prompt_version": PROMPT_VERSION,
            "prompt_fingerprint": fingerprint,
            "safety_rules_version": SAFETY_RULES_VERSION,
            "safety_topic": verdict.topic,
            "project_id": str(project_id) if project_id else None,
            "history_messages": len(history),
        },
    )

    adapter = VercelAIAdapter(
        agent=agent, run_input=run_input, accept=request.headers.get("accept"), sdk_version=7
    )
    deps = AgentDeps(
        owner_id=user.id, projects=container.projects, project_id=project_id, trace_id=trace_id
    )
    limits = UsageLimits(
        request_limit=container.settings.agent_request_limit,
        total_tokens_limit=container.settings.agent_total_tokens_limit,
    )
    completed: list[AgentRunResult[Any]] = []

    async def stream() -> AsyncIterator[BaseChunk]:
        error: str | None = None
        started = time.perf_counter()
        try:
            async for chunk in adapter.run_stream(
                message_history=history,
                model=model,
                deps=deps,
                usage_limits=limits,
                on_complete=completed.append,
            ):
                if isinstance(chunk, ErrorChunk):
                    error = chunk.error_text
                yield chunk
        finally:
            # Every turn is stored, also failed and cancelled ones: AI results cost money.
            result = completed[0] if completed and error is None else None
            status: RunStatus = (
                "completed" if result else "failed" if error is not None else "cancelled"
            )
            usage = _usage(result, deps.requests)
            duration_ms = round((time.perf_counter() - started) * 1000)
            run = AgentRun(
                trace_id=trace_id,
                owner_id=user.id,
                chat_id=chat_id,
                project_id=deps.project_id,
                status=status,
                model=model_name,
                prompt_version=PROMPT_VERSION,
                ui_messages=_turn_messages(run_input, result, status),
                model_messages=json.loads(result.new_messages_json()) if result else None,
                design_attempts=deps.design_attempts,
                usage=usage,
                error=error,
                prompt_fingerprint=fingerprint,
                safety_rules_version=SAFETY_RULES_VERSION,
                model_role=routed.role if model is not None else None,
                routing_reason=routed.reason if model is not None else None,
                duration_ms=duration_ms,
            )
            log.info(
                "agent_turn_done",
                extra={
                    "trace_id": trace_id,
                    "status": status,
                    "duration_ms": duration_ms,
                    "requests": usage.get("requests"),
                    "input_tokens": usage.get("input_tokens"),
                    "output_tokens": usage.get("output_tokens"),
                    "cache_read_tokens": usage.get("cache_read_tokens"),
                },
            )
            with anyio.CancelScope(shield=True):
                try:
                    await container.conversations.record(run)
                except Exception:
                    log.exception("agent_run_not_stored", extra={"trace_id": trace_id})

    return adapter.streaming_response(stream())


@router.get("/projects/{project_id}/chat")
async def project_chat(
    project_id: UUID, container: ContainerDep, user: UserDep
) -> list[dict[str, Any]]:
    """Chat messages of a project (Vercel AI UI message format), oldest first."""
    await container.projects.get(user.id, project_id)
    return await container.conversations.chat(user.id, project_id)
