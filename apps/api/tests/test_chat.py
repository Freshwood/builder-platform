import json

import httpx
import pytest
from homeworking.modules.agent.offline import ToolCall, decide_for_user_text


def _message(text: str, message_id: str = "m1") -> dict:  # type: ignore[type-arg]
    return {"id": message_id, "role": "user", "parts": [{"type": "text", "text": text}]}


def _events(raw: str) -> list[dict]:  # type: ignore[type-arg]
    out = []
    for line in raw.splitlines():
        if line.startswith("data: ") and line != "data: [DONE]":
            out.append(json.loads(line[6:]))
    return out


async def _chat(client: httpx.AsyncClient, text: str, project_id: str | None = None) -> list[dict]:  # type: ignore[type-arg]
    body = {"trigger": "submit-message", "id": "c1", "messages": [_message(text)]}
    if project_id:
        body["projectId"] = project_id
    response = await client.post("/api/chat", json=body)
    assert response.status_code == 200, response.text
    return _events(response.text)


def _text(events: list[dict]) -> str:  # type: ignore[type-arg]
    return "".join(e.get("delta", "") for e in events if e.get("type") == "text-delta")


def _tool_outputs(events: list[dict]) -> list[dict]:  # type: ignore[type-arg]
    return [e["output"] for e in events if e.get("type") == "tool-output-available"]


async def test_chat_creates_and_changes_project(client: httpx.AsyncClient) -> None:
    events = await _chat(client, "Ich möchte ein Hochbeet 2 × 1 m, 80 cm hoch, aus Lärche bauen.")
    outputs = _tool_outputs(events)
    assert outputs
    assert outputs[0]["action"] == "created"
    project = outputs[0]["project"]
    assert project["params"]["wood"] == "larch"
    assert "Hochbeet" in _text(events)

    events = await _chat(client, "Mach es 50 cm breiter", project_id=project["project_id"])
    outputs = _tool_outputs(events)
    assert outputs[0]["action"] == "changed"
    assert outputs[0]["diff"]["changed_params"]["width_mm"] == {"before": 1000, "after": 1500}

    stored = (await client.get(f"/api/projects/{project['project_id']}")).json()
    assert stored["project"]["inputs"]["params"]["width_mm"] == 1500


async def test_chat_asks_for_missing_dimensions(client: httpx.AsyncClient) -> None:
    events = await _chat(client, "Ich will ein Hochbeet bauen")
    assert not _tool_outputs(events)
    assert "Wie lang" in _text(events)


async def test_safety_gate_blocks_electrical_work(client: httpx.AsyncClient) -> None:
    events = await _chat(client, "Wie schließe ich eine Steckdose am Hochbeet an 230V an?")
    assert not _tool_outputs(events)
    assert "Elektrofachkräfte" in _text(events)


async def test_change_without_project_reports_error(client: httpx.AsyncClient) -> None:
    events = await _chat(client, "Mach es 50 cm breiter")
    assert "error" in _tool_outputs(events)[0]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Hochbeet 2,4 x 1,2 m, 90 cm hoch",
            {"length_mm": 2400, "width_mm": 1200, "height_mm": 900},
        ),
        (
            "hochbeet 120x80cm höhe 60 cm mit sitzkante",
            {"length_mm": 1200, "width_mm": 800, "height_mm": 600, "top_cap": True},
        ),
        ("Hochbeet 1 × 2 m ohne Folie", {"length_mm": 2000, "width_mm": 1000, "liner": False}),
    ],
)
def test_offline_planner_parses_dimensions(text: str, expected: dict) -> None:  # type: ignore[type-arg]
    decision = decide_for_user_text(text)
    assert isinstance(decision, list)
    assert decision[0] == ToolCall(
        "create_project", {"pack_id": "raised_bed", "title": "Hochbeet", "params": expected}
    )


def test_offline_planner_relative_change() -> None:
    assert decide_for_user_text("bitte 20 cm niedriger") == [
        ToolCall(
            "change_project",
            {"command": {"type": "change_parameter_by", "name": "height_mm", "delta": -200}},
        )
    ]
