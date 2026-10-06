import httpx
import pytest

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


async def test_list_projects_has_summary(client: httpx.AsyncClient) -> None:
    project_id = (await _create(client))["project"]["id"]
    listing = (await client.get("/api/projects")).json()
    assert [p["id"] for p in listing] == [project_id]
    assert listing[0]["summary"].startswith("Hochbeet")


async def test_concurrent_append_is_rejected(settings) -> None:  # type: ignore[no-untyped-def]
    from construction_model.commands import Rename
    from homeworking.bootstrap import build_container
    from homeworking.modules.projects.ports import ConcurrentModificationError

    container = build_container(settings)
    await container.create_schema()
    try:
        owner = (await container.identity.create_guest()).id
        created = await container.projects.create(owner, pack_id="raised_bed", title="A", params={})
        first = await container.projects.execute(owner, created.project.id, Rename(title="B"))
        # A second writer that read the log before `first` was appended reuses its seq.
        stale = container.projects._record(
            first.seq, Rename(title="C"), "user", "raised_bed", None, first.diff
        )
        inputs = first.project.inputs.model_copy(update={"title": "C"})
        with pytest.raises(ConcurrentModificationError):
            await container.projects._repo.append(
                first.project.model_copy(update={"inputs": inputs}), stale
            )
        model, undoable = await container.projects.view(owner, created.project.id)
        assert model.inputs.title == "B"
        assert undoable is True
    finally:
        await container.close()


async def test_templates_and_free_design(client: httpx.AsyncClient) -> None:
    keys = {t["key"] for t in (await client.get("/api/templates")).json()}
    assert keys >= {"shelf", "garden_bench", "workbench"}

    created = await client.post(
        "/api/projects",
        json={
            "pack_id": "template",
            "template_key": "shelf",
            "title": "Bücherregal",
            "params": {"width_mm": 900},
        },
    )
    assert created.status_code == 201, created.text
    project = created.json()["project"]
    assert project["result"]["trust"] == "template"
    assert project["inputs"]["pack_id"] == "design"
    assert project["result"]["solids"]
    project_id = project["id"]

    changed = await client.post(
        f"/api/projects/{project_id}/commands",
        json={"command": {"type": "change_parameter_by", "name": "shelves", "delta": 1}},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["project"]["inputs"]["params"]["shelves"] == 6

    svg = await client.get(f"/api/projects/{project_id}/drawings/iso.svg")
    assert svg.status_code == 200
    assert "<polygon" in svg.text
    assert "<circle" in svg.text

    pdf = await client.get(f"/api/projects/{project_id}/document.pdf")
    assert pdf.status_code == 200


async def test_rejected_design_returns_engine_errors(client: httpx.AsyncClient) -> None:
    design = {
        "object_type": "Kiste",
        "summary": "Kiste",
        "params": [],
        "parts": [
            {
                "id": "a",
                "name": "Brett",
                "material": "board_spruce_18x96",
                "size": [500, 96, 18],
                "at": [0, 0, 0],
            },
            {
                "id": "b",
                "name": "Brett",
                "material": "board_spruce_18x96",
                "size": [500, 96, 18],
                "at": [0, 0, 300],
            },
        ],
    }
    response = await client.post(
        "/api/projects", json={"pack_id": "design", "title": "Kiste", "design": design}
    )
    assert response.status_code == 422
    assert "nicht alle bauteile sind verbunden" in " ".join(response.json()["detail"]).lower()

    missing = await client.post("/api/projects", json={"pack_id": "design", "title": "x"})
    assert missing.status_code == 422


async def test_pdf_render_failure_is_reported_as_json(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing render must not answer with plain text (the browser saves it as document.txt)."""
    from homeworking.api import projects as projects_api

    def broken(*_args: object, **_kwargs: object) -> bytes:
        raise RuntimeError("boom")

    monkeypatch.setattr(projects_api, "render_pdf", broken)
    created = await client.post("/api/projects", json={"pack_id": "raised_bed", "title": "A"})
    pdf = await client.get(f"/api/projects/{created.json()['project']['id']}/document.pdf")
    assert pdf.status_code == 500
    assert pdf.headers["content-type"] == "application/json"
    assert "PDF" in pdf.json()["detail"]


async def test_pdf_download_headers(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/api/projects", json={"pack_id": "template", "template_key": "shelf", "title": "Regal"}
    )
    project_id = created.json()["project"]["id"]
    pdf = await client.get(f"/api/projects/{project_id}/document.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["content-disposition"].endswith('.pdf"')
    assert pdf.content.startswith(b"%PDF-")


async def test_user_price_via_command_and_undo(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/api/projects", json={"pack_id": "template", "template_key": "shelf", "title": "Regal"}
    )
    project = created.json()["project"]
    line = project["result"]["bom"][0]
    assert line["price_source"] == "estimate"
    assert line["search_query"]

    priced = await client.post(
        f"/api/projects/{project['id']}/commands",
        json={"command": {"type": "set_price", "item_id": line["item_id"], "unit_price": "39.90"}},
    )
    assert priced.status_code == 200, priced.text
    result = priced.json()["project"]["result"]
    new_line = next(b for b in result["bom"] if b["item_id"] == line["item_id"])
    assert new_line["price_source"] == "user"
    assert new_line["unit_price"] == {"min": "39.90", "max": "39.90", "currency": "EUR"}
    assert result["costs"]["user_priced"] == 1

    undone = await client.post(f"/api/projects/{project['id']}/undo")
    assert undone.json()["project"]["result"]["costs"]["user_priced"] == 0
