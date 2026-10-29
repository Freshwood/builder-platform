"""Hand-checked designs used as test corpus only.

They were curated templates before ADR-0008. The agent never sees them: every project is designed
from scratch, these files only keep the engine honest across a range of real constructions.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from homeworking.construction_model.assembly import AssemblyDesign

_FOLDER = Path(__file__).resolve().parents[1] / "fixtures" / "designs"


@cache
def fixture_designs() -> dict[str, AssemblyDesign]:
    """All fixture designs by key (file name without ``.json``)."""
    return {
        path.stem: AssemblyDesign.model_validate(json.loads(path.read_text("utf-8")))
        for path in sorted(_FOLDER.glob("*.json"))
    }


def fixture_design(key: str) -> AssemblyDesign:
    return fixture_designs()[key]
