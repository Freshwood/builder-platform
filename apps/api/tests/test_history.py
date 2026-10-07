from uuid import uuid4

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from homeworking.bootstrap import build_container
from homeworking.modules.agent.history import (
    DESIGN_STUB,
    LOOKUP_STUB,
    SUPERSEDED_STUB,
    compact_history,
)
from homeworking.modules.agent.tools import AgentDeps, build_agent
from homeworking.settings import Settings

DESIGN = {"object_type": "Regal", "parts": [{"id": "side"}] * 20}


def _design_call(call_id: str) -> ModelResponse:
    return ModelResponse(
        parts=[ToolCallPart("save_design", {"title": "Regal", "design": DESIGN}, call_id)]
    )


def _return(tool: str, call_id: str, content: object) -> ModelRequest:
    return ModelRequest(parts=[ToolReturnPart(tool, content, call_id)])


def _conversation() -> list[ModelMessage]:
    return [
        ModelRequest(parts=[UserPromptPart("Ein Regal")]),
        ModelResponse(parts=[ThinkingPart("überlege"), ToolCallPart("list_materials", {}, "m1")]),
        _return("list_materials", "m1", "Katalog ..." * 100),
        _design_call("d1"),
        _return("save_design", "d1", {"action": "created"}),
        ModelResponse(parts=[TextPart("Fertig.")]),
        # Current turn: two attempts, the first one rejected.
        ModelRequest(parts=[UserPromptPart("Mit Schublade")]),
        _design_call("d2"),
        _return("save_design", "d2", {"error": "abgelehnt", "errors": ["Kollision"]}),
        _design_call("d3"),
    ]


def _args(message: ModelMessage) -> dict[str, object]:
    part = message.parts[0]
    assert isinstance(part, ToolCallPart)
    return part.args_as_dict()


def test_earlier_turns_lose_bulky_designs_lookups_and_thinking() -> None:
    compacted = compact_history(_conversation())
    assert not any(isinstance(p, ThinkingPart) for p in compacted[1].parts)
    lookup = compacted[2].parts[0]
    assert isinstance(lookup, ToolReturnPart)
    assert lookup.content == LOOKUP_STUB
    assert _args(compacted[3]) == {"title": "Regal", "design": DESIGN_STUB}


def test_current_turn_keeps_only_the_latest_design_and_all_errors() -> None:
    compacted = compact_history(_conversation())
    assert _args(compacted[7])["design"] == SUPERSEDED_STUB
    rejected = compacted[8].parts[0]
    assert isinstance(rejected, ToolReturnPart)
    assert rejected.content == {"error": "abgelehnt", "errors": ["Kollision"]}
    assert _args(compacted[9])["design"] == DESIGN


def test_compaction_does_not_change_the_input() -> None:
    messages = _conversation()
    compact_history(messages)
    assert _args(messages[3])["design"] == DESIGN


async def test_agent_sends_compacted_history(settings: Settings) -> None:
    """The processor is wired into the agent (full designs live in design_attempts)."""
    seen: list[list[ModelMessage]] = []

    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        seen.append(messages)
        return ModelResponse(parts=[TextPart("Ok.")])

    container = build_container(settings)
    try:
        agent = build_agent(FunctionModel(respond), container.engine)
        deps = AgentDeps(
            owner_id=uuid4(), projects=container.projects, project_id=None, trace_id="t"
        )
        history = _conversation()[:6]
        await agent.run("Noch eine Frage", deps=deps, message_history=history)
        assert _args(seen[0][3])["design"] == DESIGN_STUB
        assert _args(history[3])["design"] == DESIGN
    finally:
        await container.close()
