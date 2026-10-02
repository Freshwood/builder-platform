"""Integration test against PostgreSQL (JSONB). Run with `task test:pg`."""

import os

import httpx
import pytest

from homeworking.main import create_app
from homeworking.settings import Settings

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set"),
]


async def test_flow_on_postgres() -> None:
    assert URL
    app = create_app(Settings(environment="test", database_url=URL), create_schema=True)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/projects",
                json={"pack_id": "raised_bed", "title": "PG", "params": {"length_mm": 3000}},
            )
            assert created.status_code == 201, created.text
            project_id = created.json()["project"]["id"]
            changed = await client.post(
                f"/api/projects/{project_id}/commands",
                json={"command": {"type": "set_parameters", "values": {"wood": "larch"}}},
            )
            assert changed.status_code == 200
            undone = await client.post(f"/api/projects/{project_id}/undo")
            assert undone.json()["project"]["inputs"]["params"].get("wood") is None
            listing = (await client.get("/api/projects")).json()
            assert listing[0]["summary"].startswith("Hochbeet")
            assert (await client.delete(f"/api/projects/{project_id}")).status_code == 204
