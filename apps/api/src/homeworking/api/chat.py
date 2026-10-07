"""Agent chat endpoint streaming the Vercel AI SDK UI message protocol."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import anyio
from fastapi import APIRouter, Request, Response
from pydantic import TypeAdapter
from pydantic_ai import Agent, AgentRunResult
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import TextUIPart, UIMessage
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk, ErrorChunk
from pydantic_ai.usage import RunUsage, UsageLimits

from homeworking.api.deps import ContainerDep, UserDep
from homeworking.modules.agent.offline import fixed_text_model
from homeworking.modules.agent.prompts import PROMPT_VERSION
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
    last_text = _redact_user_messages(run_input)

    project_id = _project_id(body)
    if project_id is not None:
        try:
            await container.projects.get(user.id, project_id)
        except LookupError:
            project_id = None

    trace_id = uuid4().hex
    verdict = check_message(last_text)
    agent: Agent[AgentDeps, str] = container.agent
    if verdict.blocked and verdict.response:
        agent = Agent(fixed_text_model(verdict.response), deps_type=AgentDeps)

    log.info(
        "agent_turn",
        extra={
            "trace_id": trace_id,
            "model": container.model_name if not verdict.blocked else "safety",
            "prompt_version": PROMPT_VERSION,
            "safety_rules_version": SAFETY_RULES_VERSION,
            "safety_topic": verdict.topic,
            "project_id": str(project_id) if project_id else None,
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
    chat_id = str(body.get("id") or "")[:128] or None
    model_name = container.model_name if not verdict.blocked else "safety"
    completed: list[AgentRunResult[Any]] = []

    async def stream() -> AsyncIterator[BaseChunk]:
        error: str | None = None
        try:
            async for chunk in adapter.run_stream(
                deps=deps, usage_limits=limits, on_complete=completed.append
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
                usage=_usage_adapter.dump_python(result.usage, mode="json") if result else None,
                error=error,
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
