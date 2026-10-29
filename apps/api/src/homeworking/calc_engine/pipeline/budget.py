"""How long may a design take? Decided by rules, never by the LLM.

Every construction has to be finished for the customer within a fixed time, measured from the
chat message to the stored project. The limit depends on the category of the brief: usual
furniture and small constructions are ``medium``, buildings and large timber structures are
``heavy``. The values are part of the behaviour tests (``tests/bdd/features/zeitbudget.feature``)
and of the live evaluation (``homeworking_dev.live_eval``); change them only together with those.
"""

from __future__ import annotations

import re
from typing import Literal

from homeworking.construction_model.pipeline import Spec

Complexity = Literal["medium", "heavy"]

# Seconds from the customer's message to a finished project.
TIME_BUDGET_S: dict[Complexity, int] = {"medium": 60, "heavy": 90}

# A dimension from this size on (mm) makes a construction heavy, whatever it is called.
HEAVY_FROM_MM = 3_000

# Buildings and large timber structures. "haus" is matched as a word part only where it names a
# building (Gartenhaus, Fachwerkhaus, Spielhaus), not "Haustür" or "Hausschuh".
_HEAVY = re.compile(
    r"fachwerk|(?<![a-zäöüß])haus(?![a-zäöüß])|(?:garten|spiel|holz|block|wochenend|bienen)haus"
    r"|h(?:ü|ue)tte|carport|garage|schuppen|scheune|pavillon|pergola|wintergarten|anbau"
    r"|dachstuhl|stall\b|\bzaun",
    re.IGNORECASE,
)


def classify(spec: Spec) -> Complexity:
    """The category of a brief: ``heavy`` for buildings and anything large, else ``medium``."""
    if any(value >= HEAVY_FROM_MM for value in spec.dimensions().values()):
        return "heavy"
    return "heavy" if _HEAVY.search(spec.description) else "medium"


def time_budget_s(spec: Spec) -> int:
    return TIME_BUDGET_S[classify(spec)]
