"""Versions, re-planning within a project and stored agent runs (docs/problems/versioning.md)."""

import json

import httpx

from homeworking.api.chat import ABORTED_TEXT


def _body(text: str, project_id: str | None = None, chat_id: str = "c1") -> dict:  # type: ignore[type-arg]
    body: dict = {  # type: ignore[type-arg]
        "trigger": "submit-message",
        "id": chat_id,
        "messages": [{"id": "m1", "role": "user", "parts": [{"type": "text", "text": text}]}],
    }
    if project_id:
        body["projectId"] = project_id
    return body


async def _chat(client: httpx.AsyncClient, text: str, project_id: str | None = None) -> list[dict]:  # type: ignore[type-arg]
    response = await client.post("/api/chat", json=_body(text, project_id))
    assert response.status_code == 200, response.text
    return [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]


def _outputs(events: list[dict]) -> list[dict]:  # type: ignore[type-arg]
    return [e["output"] for e in events if e.get("type") == "tool-output-available"]


async def test_chat_is_stored_per_project_including_earlier_questions(
    client: httpx.AsyncClient,
) -> None:
    # A question without a project, then the project: both turns form the project's chat
    await _chat(client, "Ich will ein Hochbeet bauen")
    events = await _chat(client, "Hochbeet 2 × 1 m, 80 cm hoch, aus Lärche")
    project_id = _outputs(events)[0]["project"]["project_id"]
    await _chat(client, "Mach es 50 cm breiter", project_id)

    chat = (await client.get(f"/api/projects/{project_id}/chat")).json()
    assert [m["role"] for m in chat] == ["user", "assistant"] * 3
    assert chat[0]["parts"][0]["text"] == "Ich will ein Hochbeet bauen"
    # Tool calls with their results are restored, so the UI shows the same activity again
    tools = [p for m in chat for p in m["parts"] if p["type"].startswith("tool-")]
    assert any(p.get("output", {}).get("action") == "created" for p in tools)
    assert any(p.get("output", {}).get("action") == "changed" for p in tools)


async def test_chat_of_another_user_is_hidden(
    client: httpx.AsyncClient,
    settings,  # type: ignore[no-untyped-def]
) -> None:
    events = await _chat(client, "Hochbeet 2 × 1 m, 80 cm hoch, aus Lärche")
    project_id = _outputs(events)[0]["project"]["project_id"]
    client.cookies.clear()
    assert (await client.get(f"/api/projects/{project_id}/chat")).status_code == 404


async def test_new_request_in_a_project_becomes_its_next_version(
    client: httpx.AsyncClient,
) -> None:
    first = _outputs(await _chat(client, "Hochbeet 2 × 1 m, 80 cm hoch, aus Lärche"))[0]
    project_id = first["project"]["project_id"]
    second = _outputs(
        await _chat(client, "Ich brauche ein Regal 100 x 35 x 200 cm mit 6 Böden", project_id)
    )[0]
    assert second["action"] == "replanned"
    assert second["project"]["project_id"] == project_id

    projects = (await client.get("/api/projects")).json()
    assert [p["id"] for p in projects] == [project_id]
    assert projects[0]["pack_id"] == "design"

    versions = (await client.get(f"/api/projects/{project_id}/versions")).json()
    assert versions[-1]["label"].startswith("Projekt „")
    assert any(v["label"].startswith("Neu geplant") for v in versions)
    assert versions[0]["current"] is True


async def test_view_and_restore_an_earlier_version(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/api/projects",
        json={"pack_id": "template", "template_key": "shelf", "title": "Regal", "params": {}},
    )
    project_id = created.json()["project"]["id"]
    width = created.json()["project"]["result"]["effective_params"]["width_mm"]
    await client.post(
        f"/api/projects/{project_id}/commands",
        json={"command": {"type": "set_parameters", "values": {"width_mm": 1200}}},
    )

    old = (await client.get(f"/api/projects/{project_id}/versions/1")).json()
    assert old["project"]["result"]["effective_params"]["width_mm"] == width
    assert old["can_undo"] is False
    svg = await client.get(f"/api/projects/{project_id}/drawings/front.svg?seq=1")
    assert svg.status_code == 200
    assert (await client.get(f"/api/projects/{project_id}/versions/9")).status_code == 404

    restored = (await client.post(f"/api/projects/{project_id}/versions/1/restore")).json()
    assert restored["seq"] == 3
    assert restored["project"]["result"]["effective_params"]["width_mm"] == width
    versions = (await client.get(f"/api/projects/{project_id}/versions")).json()
    assert [v["label"] for v in versions][:2] == [
        "Version 1 wiederhergestellt",
        f"Geändert: Breite (mm) {width} → 1200",
    ]

    # Restoring is an ordinary change: undo brings the 1200 mm back
    undone = (await client.post(f"/api/projects/{project_id}/undo")).json()
    assert undone["project"]["inputs"]["params"]["width_mm"] == 1200


async def test_failed_turn_is_stored_with_a_note(client: httpx.AsyncClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    events = await _chat(client, "Hochbeet 2 × 1 m, 80 cm hoch, aus Lärche")
    project_id = _outputs(events)[0]["project"]["project_id"]

    from pydantic_ai.ui.vercel_ai import VercelAIAdapter

    async def broken(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("model down")
        yield  # pragma: no cover

    monkeypatch.setattr(VercelAIAdapter, "run_stream_native", broken)
    await _chat(client, "Mach es 50 cm breiter", project_id)
    chat = (await client.get(f"/api/projects/{project_id}/chat")).json()
    assert chat[-2]["parts"][0]["text"] == "Mach es 50 cm breiter"
    assert chat[-1]["parts"][0]["text"] == ABORTED_TEXT
