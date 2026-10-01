"""Project document (PDF/UA-1) generated from the project model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from construction_model.model import Origin, ProjectModel
from jinja2 import Environment, PackageLoader, select_autoescape

from homeworking.modules.compliance.disclosure import (
    AI_CONTENT_LABEL,
    AI_DOCUMENT_STATEMENT,
    DOCUMENT_NOTICES,
    NOTICES_VERSION,
)
from homeworking.modules.drawings.svg import render_svg

_env = Environment(
    loader=PackageLoader("homeworking.modules.documents", "templates"),
    autoescape=select_autoescape(["html", "j2"]),
)


def _eur(value: Decimal) -> str:
    text = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} €"


def _qty(value: Decimal) -> str:
    return f"{value.normalize():f}".replace(".", ",")


@dataclass(frozen=True)
class _DrawingView:
    title: str
    description: str
    svg: str


def render_html(project: ProjectModel, *, now: datetime | None = None) -> str:
    result = project.result
    created = (now or datetime.now(UTC)).strftime("%d.%m.%Y")
    ai_notes = [n for n in project.inputs.notes if n.origin is Origin.AI]
    drawings = [
        _DrawingView(
            title=d.title,
            description=d.description,
            svg=render_svg(d, max_width_px=680, element_id=f"pdf-{d.view}"),
        )
        for d in result.drawings
    ]
    footer = (
        f"Homeworking · {project.inputs.title} · Planungshilfe, kein Standsicherheitsnachweis"
    ).replace('"', "'")
    return _env.get_template("project.html.j2").render(
        project=project,
        result=result,
        drawings=drawings,
        ai_notes=ai_notes,
        ai_label=AI_CONTENT_LABEL,
        ai_keyword="AI-generated text: yes" if ai_notes else "AI-generated text: no",
        ai_statement=AI_DOCUMENT_STATEMENT,
        document_notices=DOCUMENT_NOTICES,
        notices_version=NOTICES_VERSION,
        created=created,
        computed=result.provenance.computed_at.strftime("%d.%m.%Y %H:%M UTC"),
        footer=footer,
        eur=_eur,
        qty=_qty,
    )


def render_pdf(project: ProjectModel, *, now: datetime | None = None) -> bytes:
    from weasyprint import HTML  # heavy import, keep lazy

    html = render_html(project, now=now)
    pdf: bytes = HTML(string=html).write_pdf(pdf_variant="pdf/ua-1")
    return pdf
