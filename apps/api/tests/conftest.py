import sys
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from homeworking.main import create_app
from homeworking.settings import Settings

# --import-mode=importlib: make the engine's hand-checked fixture designs importable in the API
# tests (``from design_fixtures import fixture_design``), and the helpers next to this file.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "calc-engine" / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture
def settings(tmp_path) -> Settings:  # type: ignore[no-untyped-def]
    return Settings(
        environment="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        llm_mode="test",
    )


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, create_schema=True)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
