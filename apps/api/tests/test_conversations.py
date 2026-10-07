import json
from uuid import uuid4

from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from homeworking.bootstrap import build_container
from homeworking.modules.conversations.service import AgentRun, RunStatus
from homeworking.settings import Settings


def _turn(question: str) -> list[object]:
    messages = [
        ModelRequest(parts=[UserPromptPart(question)]),
        ModelResponse(parts=[TextPart(f"Antwort auf {question}")]),
    ]
    return json.loads(ModelMessagesTypeAdapter.dump_json(messages))  # type: ignore[no-any-return]


def _run(owner, chat_id: str, question: str, status: RunStatus = "completed") -> AgentRun:  # type: ignore[no-untyped-def]
    return AgentRun(
        trace_id=uuid4().hex,
        owner_id=owner,
        chat_id=chat_id,
        project_id=None,
        status=status,
        model="m",
        prompt_version="p",
        ui_messages=[],
        model_messages=_turn(question) if status == "completed" else None,
    )


def _questions(messages: list) -> list[str]:  # type: ignore[type-arg]
    return [
        p.content
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, UserPromptPart)
    ]


async def test_history_is_the_owners_completed_turns_in_order(settings: Settings) -> None:
    container = build_container(settings)
    await container.create_schema()
    try:
        owner = (await container.identity.create_guest()).id
        other = (await container.identity.create_guest()).id
        conversations = container.conversations
        await conversations.record(_run(owner, "c1", "erste"))
        await conversations.record(_run(owner, "c1", "kaputt", status="failed"))
        await conversations.record(_run(owner, "c1", "zweite"))
        await conversations.record(_run(other, "c1", "fremd"))
        await conversations.record(_run(owner, "c2", "anderer Chat"))

        history = await conversations.history(owner, chat_id="c1", project_id=None)

        assert _questions(history) == ["erste", "zweite"]
        assert await conversations.history(owner, chat_id=None, project_id=None) == []
    finally:
        await container.close()
