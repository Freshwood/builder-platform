import httpx
import pytest
from sqlalchemy import select

from homeworking.db.schema import AgentRunRow
from homeworking.main import create_app
from homeworking.modules.agent.routing import route
from homeworking.settings import Settings


@pytest.mark.parametrize(
    ("text", "has_project", "role", "reason"),
    [
        # Routine tool calls on an existing project: fast model
        ("Mach es 50 cm breiter", True, "fast", "relative_change"),
        ("Bitte rückgängig machen", True, "fast", "undo"),
        ("Die Platte kostet bei mir 39,90 €", True, "fast", "price"),
        ("Nimm die günstige Variante", True, "fast", "variant"),
        ("Höhe bitte 90 cm", True, "fast", "parameters"),
        ("Lieber aus Lärche", True, "fast", "parameters"),
        ("Warum sind die Bretter 28 mm stark?", True, "fast", "question"),
        # Packs and templates: fast model
        ("Hochbeet 2 × 1 m, 80 cm hoch, aus Lärche", False, "fast", "pack_or_template"),
        ("Regal 80 × 30 × 180 cm mit 5 Böden", False, "fast", "pack_or_template"),
        # Free designs and structural changes: designer
        ("Ein Schuhschrank mit zwei Türen", False, "designer", "structural"),
        ("Füge eine Schublade hinzu", True, "designer", "structural"),
        ("Ein Vogelhaus für den Garten", False, "designer", "default"),
        ("Ein Kräuterbeet auf Rollen", False, "designer", "default"),
        # Without a project, edits make no sense: no shortcut
        ("Mach es 50 cm breiter", False, "designer", "default"),
    ],
)
def test_route(text: str, has_project: bool, role: str, reason: str) -> None:
    routed = route(text, has_project=has_project)
    assert (routed.role, routed.reason) == (role, reason)


async def test_agent_run_stores_provenance(settings: Settings) -> None:
    app = create_app(settings, create_schema=True)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            body = {
                "trigger": "submit-message",
                "id": "c1",
                "messages": [
                    {
                        "id": "m1",
                        "role": "user",
                        "parts": [{"type": "text", "text": "Hochbeet 2 × 1 m, 80 cm hoch"}],
                    }
                ],
            }
            assert (await client.post("/api/chat", json=body)).status_code == 200
        async with app.state.container.sessions() as session:
            run = (await session.scalars(select(AgentRunRow))).one()
    assert run.prompt_fingerprint
    assert run.safety_rules_version
    assert (run.model_role, run.routing_reason) == ("fast", "pack_or_template")
    assert run.duration_ms is not None
    assert run.usage is not None
    assert run.usage["requests"] == len(run.usage["per_request"]) == 2
