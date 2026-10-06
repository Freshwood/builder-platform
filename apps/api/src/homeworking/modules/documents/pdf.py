"""Project document (PDF/UA-1) generated from the project model."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from jinja2 import Environment, PackageLoader, select_autoescape

from construction_model.base import ParamValue
from construction_model.model import ConstructionResult, Origin, ParamSpec, ProjectModel
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


def _m(mm: int) -> str:
    return f"{mm / 1000:.2f}".replace(".", ",") + " m"


def _qty(value: Decimal) -> str:
    return f"{value.normalize():f}".replace(".", ",")


@dataclass(frozen=True)
class _DrawingView:
    title: str
    description: str
    svg: str


def _param_value(spec: ParamSpec, value: ParamValue | None) -> str:
    if value is None:
        return "–"
    if spec.kind == "bool":
        return "ja" if value else "nein"
    if spec.kind == "choice":
        return next((o.label for o in spec.options if o.value == value), str(value))
    if spec.kind == "length":
        return f"{value} mm"
    if spec.kind == "angle":
        return f"{value}°"
    return str(value)


def _params(result: ConstructionResult) -> list[tuple[str, str]]:
    """Adjustable parameters with their effective values, as shown in the web app."""
    return [
        (spec.label, _param_value(spec, result.effective_params.get(spec.name)))
        for spec in result.param_specs
    ]


TRUST_LABELS = {
    "pack": "Geprüftes Construction Pack",
    "template": "Vorlage aus der Homeworking-Sammlung",
    "ai_draft": "KI-Entwurf – Konstruktion nicht fachlich geprüft",
}


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
        ai_keyword=(
            "AI-generated text: yes"
            if ai_notes or result.trust == "ai_draft"
            else "AI-generated text: no"
        ),
        trust_label=TRUST_LABELS[result.trust],
        ai_statement=AI_DOCUMENT_STATEMENT,
        document_notices=DOCUMENT_NOTICES,
        notices_version=NOTICES_VERSION,
        created=created,
        computed=result.provenance.computed_at.strftime("%d.%m.%Y %H:%M UTC"),
        footer=footer,
        params=_params(result),
        eur=_eur,
        qty=_qty,
        m=_m,
    )


def warm_up() -> None:
    """Import WeasyPrint and load fonts once, so the first real download is not slow.

    The first render in a process costs several seconds (module import, fontconfig), on WSL
    with the repository under /mnt/c much more - long enough to hit proxy timeouts.
    """
    try:
        from weasyprint import HTML

        HTML(string="<p>warm-up</p>").write_pdf()
    except Exception:  # pragma: no cover - only logged; the real request reports errors
        logging.getLogger("homeworking.documents").warning("pdf_warm_up_failed", exc_info=True)


def render_pdf(project: ProjectModel, *, now: datetime | None = None) -> bytes:
    from weasyprint import HTML  # heavy import, keep lazy

    html = render_html(project, now=now)
    pdf: bytes = HTML(string=html).write_pdf(pdf_variant="pdf/ua-1")
    return pdf
