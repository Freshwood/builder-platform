"""Which questions are still open in a brief? Decided by rules, never by the LLM.

The intake model fills a :class:`~construction_model.pipeline.Spec` from the customer's text and
only *words* the questions that this module returns. That keeps the question count small and the
decision reproducible.
"""

from __future__ import annotations

from collections.abc import Mapping

from construction_model.pipeline import Option, Question, Spec

USE_OPTIONS = [
    Option(value="indoor", label="Innen"),
    Option(value="outdoor", label="Außen"),
]
SUPPORT_OPTIONS = [
    Option(value="floor", label="Freistehend"),
    Option(value="wall", label="An der Wand"),
]
FINISH_OPTIONS = [
    Option(value="natural", label="Unbehandelt"),
    Option(value="oil", label="Geölt"),
    Option(value="glaze", label="Lasiert"),
    Option(value="paint", label="Deckend lackiert"),
]
EXPERIENCE_OPTIONS = [
    Option(value="beginner", label="Einsteiger"),
    Option(value="advanced", label="Geübt"),
    Option(value="pro", label="Profi"),
]
PANEL_OPTION = Option(value="panel", label="Plattenwerkstoff")

DEFAULT_LIMIT = 3


def _dimension_question(spec: Spec) -> Question | None:
    given = spec.dimensions()
    if len(given) == 3:
        return None
    if not given:
        return Question(
            field="size",
            text="Welche Maße soll es haben (Breite, Tiefe, Höhe)? Ungefähre Angaben reichen.",
            blocking=True,
        )
    names = {"width_mm": "Breite", "depth_mm": "Tiefe", "height_mm": "Höhe"}
    missing = [label for key, label in names.items() if key not in given]
    return Question(field="size", text=f"Welche {' und '.join(missing)} soll es haben?")


def open_questions(
    spec: Spec, species: Mapping[str, str] | None = None, *, limit: int = DEFAULT_LIMIT
) -> list[Question]:
    """The most important open questions, blocking ones first (at most ``limit``)."""
    candidates: list[Question | None] = [
        _dimension_question(spec),
        None
        if spec.use is not None
        else Question(field="use", text="Wo wird es aufgestellt?", options=USE_OPTIONS),
        None
        if spec.support is not None
        else Question(field="support", text="Wie wird es montiert?", options=SUPPORT_OPTIONS),
        None
        if spec.wood is not None
        else Question(
            field="wood",
            text="Aus welchem Material soll es sein?",
            options=[*(Option(value=k, label=v) for k, v in (species or {}).items()), PANEL_OPTION][
                :8
            ],
        ),
        None
        if spec.finish is not None
        else Question(field="finish", text="Welche Oberfläche?", options=FINISH_OPTIONS),
        None
        if spec.experience is not None
        else Question(
            field="experience", text="Wie viel Erfahrung hast du?", options=EXPERIENCE_OPTIONS
        ),
    ]
    questions = [q for q in candidates if q is not None]
    questions.sort(key=lambda q: not q.blocking)  # stable: keeps the priority order otherwise
    return questions[:limit]


def is_ready(spec: Spec) -> bool:
    """A design is possible: the scale of the object is known (everything else has defaults)."""
    return bool(spec.dimensions())
