"""Response size and caching of the endpoints the workspace polls (review 2026-10-07)."""

import json

import httpx


async def _create(client: httpx.AsyncClient) -> dict:  # type: ignore[type-arg]
    response = await client.post(
        "/api/projects",
        json={"pack_id": "raised_bed", "title": "Hochbeet", "params": {"width_mm": 1000}},
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


async def test_project_view_has_no_drawing_primitives(client: httpx.AsyncClient) -> None:
    created = await _create(client)
    project_id = created["project"]["id"]
    for body in (created, (await client.get(f"/api/projects/{project_id}")).json()):
        drawings = body["project"]["result"]["drawings"]
        assert drawings
        assert all("primitives" not in d for d in drawings)
        assert body["seq"] >= 1


async def test_json_is_compressed_but_the_chat_stream_is_not(client: httpx.AsyncClient) -> None:
    project_id = (await _create(client))["project"]["id"]
    response = await client.get(f"/api/projects/{project_id}", headers={"accept-encoding": "gzip"})
    assert response.headers["content-encoding"] == "gzip"

    chat = await client.post(
        "/api/chat",
        headers={"accept-encoding": "gzip"},
        json={
            "trigger": "submit-message",
            "id": "c1",
            "messages": [
                {"id": "m1", "role": "user", "parts": [{"type": "text", "text": "Hallo"}]}
            ],
        },
    )
    # Compressing server-sent events would buffer them and stall the live answer.
    assert "content-encoding" not in chat.headers


async def test_drawing_of_a_fixed_version_is_cacheable(client: httpx.AsyncClient) -> None:
    project_id = (await _create(client))["project"]["id"]
    current = await client.get(f"/api/projects/{project_id}/drawings/plan.svg?v=1")
    assert current.headers["cache-control"] == "private, no-cache"
    fixed = await client.get(f"/api/projects/{project_id}/drawings/plan.svg?seq=1")
    assert fixed.status_code == 200
    assert "immutable" in fixed.headers["cache-control"]


async def test_earlier_version_is_stable_and_compact(client: httpx.AsyncClient) -> None:
    project_id = (await _create(client))["project"]["id"]
    await client.post(
        f"/api/projects/{project_id}/commands",
        json={"command": {"type": "set_parameters", "values": {"width_mm": 1200}}},
    )
    first = (await client.get(f"/api/projects/{project_id}/versions/1")).json()
    again = (await client.get(f"/api/projects/{project_id}/versions/1")).json()
    assert first == again
    assert json.dumps(first).count("primitives") == 0
    assert first["project"]["inputs"]["params"]["width_mm"] == 1000


def test_log_lines_carry_extra_fields() -> None:
    import logging

    from homeworking.logging_config import JsonFormatter

    record = logging.LogRecord("homeworking.agent", logging.INFO, "", 0, "agent_turn", None, None)
    record.trace_id = "abc"
    line = json.loads(JsonFormatter().format(record))
    assert (line["event"], line["trace_id"]) == ("agent_turn", "abc")
