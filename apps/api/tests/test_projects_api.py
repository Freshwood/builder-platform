import httpx

CREATE = {
    "pack_id": "raised_bed",
    "title": "Hochbeet Test",
    "params": {"length_mm": 2000, "width_mm": 1000, "height_mm": 800},
}


async def _create(client: httpx.AsyncClient) -> dict:  # type: ignore[type-arg]
    response = await client.post("/api/projects", json=CREATE)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


async def test_health_and_guest_session(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/health")).json() == {"status": "ok"}
    me1 = (await client.get("/api/me")).json()
    me2 = (await client.get("/api/me")).json()
    assert me1["id"] == me2["id"]
    assert me1["is_guest"] is True


async def test_create_change_undo_flow(client: httpx.AsyncClient) -> None:
    created = await _create(client)
    project_id = created["project"]["id"]
    assert created["project"]["result"]["key_figures"]["Wandhöhe"].startswith("870")

    changed = await client.post(
        f"/api/projects/{project_id}/commands",
        json={"command": {"type": "change_parameter_by", "name": "width_mm", "delta": 500}},
    )
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert body["project"]["inputs"]["params"]["width_mm"] == 1500
    assert body["diff"]["params"] == [{"name": "width_mm", "before": 1000, "after": 1500}]
    assert body["can_undo"] is True

    undone = (await client.post(f"/api/projects/{project_id}/undo")).json()
    assert undone["project"]["inputs"]["params"]["width_mm"] == 1000
    assert undone["can_undo"] is False

    history = (await client.get(f"/api/projects/{project_id}/history")).json()
    assert [h["command"]["type"] for h in history] == [
        "create_project",
        "change_parameter_by",
        "undo",
    ]
    assert (await client.post(f"/api/projects/{project_id}/undo")).status_code == 409


async def test_select_variant_and_invalid_params(client: httpx.AsyncClient) -> None:
    project_id = (await _create(client))["project"]["id"]
    selected = await client.post(
        f"/api/projects/{project_id}/commands",
        json={"command": {"type": "select_variant", "variant_key": "durable"}},
    )
    variants = {v["key"]: v for v in selected.json()["project"]["result"]["variants"]}
    assert variants["durable"]["is_selected"] is True

    bad = await client.post(
        f"/api/projects/{project_id}/commands",
        json={"command": {"type": "set_parameters", "values": {"width_mm": 99999}}},
    )
    assert bad.status_code == 422
    assert "width_mm" in bad.json()["detail"][0]


async def test_projects_are_private_per_session(
    client: httpx.AsyncClient,
    settings,  # type: ignore[no-untyped-def]
) -> None:
    project_id = (await _create(client))["project"]["id"]
    client.cookies.clear()
    assert (await client.get(f"/api/projects/{project_id}")).status_code == 404
    assert (await client.get("/api/projects")).json() == []


async def test_svg_export_and_delete(client: httpx.AsyncClient) -> None:
    project_id = (await _create(client))["project"]["id"]
    svg = await client.get(f"/api/projects/{project_id}/drawings/plan.svg")
    assert svg.headers["content-type"].startswith("image/svg+xml")
    assert "<title" in svg.text
    assert (await client.get(f"/api/projects/{project_id}/drawings/nope.svg")).status_code == 404

    export = (await client.get(f"/api/projects/{project_id}/export")).json()
    assert export["format"] == "homeworking.project-export"
    assert len(export["commands"]) == 1

    assert (await client.delete(f"/api/projects/{project_id}")).status_code == 204
    assert (await client.get(f"/api/projects/{project_id}")).status_code == 404
