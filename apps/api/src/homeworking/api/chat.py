"""Agent chat endpoint streaming the Vercel AI SDK UI message protocol."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, Response
from pydantic_ai import Agent
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import TextUIPart
from pydantic_ai.usage import UsageLimits

from homeworking.api.deps import ContainerDep, UserDep
from homeworking.modules.agent.offline import fixed_text_model
from homeworking.modules.agent.prompts import PROMPT_VERSION
from homeworking.modules.agent.tools import AgentDeps
from homeworking.modules.compliance.redaction import redact
from homeworking.modules.compliance.safety import SAFETY_RULES_VERSION, check_message

router = APIRouter(prefix="/api", tags=["agent"])
log = logging.getLogger("homeworking.agent")


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
    return adapter.streaming_response(adapter.run_stream(deps=deps, usage_limits=limits))
