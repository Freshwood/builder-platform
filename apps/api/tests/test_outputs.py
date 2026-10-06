import uuid
from datetime import UTC, datetime

import pytest
from syrupy.extensions.single_file import SingleFileSnapshotExtension, WriteMode

from calc_engine.engine import default_engine
from construction_model.model import Note, Origin, ProjectInputs, ProjectModel
from homeworking.modules.compliance.redaction import redact
from homeworking.modules.compliance.safety import check_message
from homeworking.modules.documents.pdf import render_html, render_pdf
from homeworking.modules.drawings.svg import render_svg

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
PROJECT_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


class SvgSnapshot(SingleFileSnapshotExtension):
    file_extension = "svg"
    _write_mode = WriteMode.TEXT


def _project(**params: object) -> ProjectModel:
    engine = default_engine(clock=lambda: NOW)
    inputs = ProjectInputs(
        title="Hochbeet Referenz",
        pack_id="raised_bed",
        params={"length_mm": 2400, "width_mm": 1000, "height_mm": 800, **params},  # type: ignore[dict-item]
        notes=[
            Note(id=PROJECT_ID, origin=Origin.AI, text="Lärche wegen Haltbarkeit.", created_at=NOW)
        ],
    )
    return ProjectModel(id=PROJECT_ID, inputs=inputs, result=engine.build(inputs))


@pytest.mark.parametrize("view", ["plan", "front", "side", "corner_detail"])
def test_svg_golden(view: str, snapshot) -> None:  # type: ignore[no-untyped-def]
    drawing = next(d for d in _project(top_cap=True).result.drawings if d.view == view)
    svg = render_svg(drawing, element_id=view)
    assert svg == snapshot(extension_class=SvgSnapshot)


def test_svg_is_accessible() -> None:
    drawing = _project().result.drawings[0]
    svg = render_svg(drawing, element_id="x")
    assert 'role="img"' in svg
    assert '<title id="x-title">Draufsicht</title>' in svg
    assert 'aria-labelledby="x-title x-desc"' in svg


def test_document_html_contains_mandatory_blocks() -> None:
    html = render_html(_project(), now=NOW)
    assert "kein Standsicherheitsnachweis" in html
    assert "Art. 50 KI-Verordnung" in html
    assert "KI-generiert" in html
    assert "AI-generated text: yes" in html
    assert "Landesbauordnung" in html


def test_pdf_is_generated() -> None:
    pdf = render_pdf(_project(), now=NOW)
    assert pdf.startswith(b"%PDF-1.7")
    assert len(pdf) > 20_000


@pytest.mark.parametrize(
    ("text", "topic"),
    [
        ("Ich will eine Steckdose setzen", "electrical"),
        ("Gasleitung verlegen im Garten", "gas_fire"),
        ("Tragende Wand entfernen für Durchgang", "structural"),
        ("Eternit-Platten vom Schuppen abschrauben", "hazardous"),
        ("Hochbeet 2 x 1 m aus Lärche", None),
    ],
)
def test_safety_classifier(text: str, topic: str | None) -> None:
    assert check_message(text).topic == topic


def test_redaction() -> None:
    text = "Ich bin max@example.org, Tel. 0171 1234567, wohne Lindenstraße 12a."
    redacted = redact(text)
    assert "max@example.org" not in redacted
    assert "1234567" not in redacted
    assert "Lindenstraße 12a" not in redacted
    assert redact("Hochbeet 2000 x 1000 mm, 0,8 m hoch") == "Hochbeet 2000 x 1000 mm, 0,8 m hoch"


def test_document_contains_all_sections() -> None:
    html = render_html(_project(), now=NOW)
    for heading in (
        "Eckdaten",
        "Maße und Einstellungen",
        "Varianten",
        "Zeichnungen",
        "Materialliste",
        "Zuschnittliste",
        "Einkauf und Schnittplan",
        "Werkzeug",
        "Bauanleitung",
        "Nachvollziehbarkeit",
    ):
        assert heading in html, heading
