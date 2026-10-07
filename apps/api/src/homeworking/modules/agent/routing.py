"""Pick the model for a chat turn (ADR-0006), deterministically and without an extra LLM call.

Free-form designs are the hard part: long structured JSON, geometry, repair rounds. They stay on
the designer model. Turns that only pick a template, change parameters, prices or variants,
undo, or ask about the project are routine tool calls; a fast, cheaper model handles them.
When in doubt the designer is used: a wrong "fast" decision costs quality, a wrong "designer"
decision only costs money.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from homeworking.modules.agent.offline import _DELTA, _VARIANTS, _match_template

Role = Literal["designer", "fast"]

ROUTING_VERSION = "1"

# Words that ask for a new or changed construction (beyond template parameters).
_STRUCTURAL = re.compile(
    r"entw(?:u|ü|ue)rf|konstru|umbau|bau(?:e|t)?\s+(?:mir|eine?n?)\b.*\b(?:mit|ohne)\b|"
    r"zus(?:ä|ae)tzlich|schublade|klappe|t(?:ü|ue)r(?:en)?\b|fach\b|f(?:ä|ae)cher|"
    r"(?:statt|anstatt|anders|andere\s+bauweise)",
    re.IGNORECASE,
)
_UNDO = re.compile(r"r(?:ü|ue)ckg(?:ä|ae)ngig|undo", re.IGNORECASE)
_PRICE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:€|eur|euro)\b|kostet\s+bei\s+mir", re.IGNORECASE)
_PARAMS = re.compile(
    r"\b(?:breite|l(?:ä|ae)nge|h(?:ö|oe)he|tiefe|st(?:ä|ae)rke|holzart|lasur|(?:ö|oe)l|"
    r"unbehandelt|l(?:ä|ae)rche|douglasie|fichte|kiefer|eiche)\b.*\d|"
    r"\b(?:in|aus)\s+(?:l(?:ä|ae)rche|douglasie|fichte|kiefer|eiche)\b",
    re.IGNORECASE,
)
_QUESTION = re.compile(
    r"^\s*(?:warum|wieso|weshalb|was|wie\s+viel|wieviel|welche|kann\s+ich|muss\s+ich)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Route:
    role: Role
    reason: str


def route(text: str, *, has_project: bool) -> Route:
    """Role for a user message; ``has_project`` = an active project is being edited."""
    lowered = text.lower()
    if _STRUCTURAL.search(lowered):
        return Route("designer", "structural")
    if has_project:
        if _UNDO.search(lowered):
            return Route("fast", "undo")
        if _DELTA.search(lowered):
            return Route("fast", "relative_change")
        if _PRICE.search(lowered):
            return Route("fast", "price")
        if any(word in lowered for word in _VARIANTS) and "variante" in lowered:
            return Route("fast", "variant")
        if _PARAMS.search(lowered):
            return Route("fast", "parameters")
        if _QUESTION.search(lowered):
            return Route("fast", "question")
    if "hochbeet" in lowered or _match_template(lowered) is not None:
        return Route("fast", "pack_or_template")
    return Route("designer", "default")
