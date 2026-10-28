"""Offline token measurement of the pipeline stages (``tests/test_stage_budget.py``).

Replays one realistic request per stage through the real agent with the offline stage model and
meters it like ``agent/bench.py``. The request side (instructions, output schema, prompt) is
exact; the output side is the offline model's short answer, i.e. a lower bound.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

from pydantic_ai.models.function import FunctionModel

from calc_engine.pipeline.gaps import open_questions
from construction_model.pipeline import Spec
from homeworking.modules.agent.metering import Meter
from homeworking.modules.agent.model import Models
from homeworking.modules.pipeline import offline
from homeworking.modules.pipeline.stages import Pipeline
from homeworking.settings import Settings

SPECIES = {
    "spruce": "Fichte",
    "pine": "Kiefer",
    "douglas": "Douglasie",
    "larch": "Lärche",
    "oak": "Eiche",
    "beech": "Buche",
    "robinia": "Robinie",
}
DESCRIPTION = (
    "Ich möchte ein Podest für Kinder für eine Modenschau bauen, so eine Art Tribüne für einen "
    "Catwalk. Es soll maximal 2 m lang und 1 m breit sein und wird drinnen aufgestellt."
)


def _metered(model: FunctionModel, meter: Meter) -> FunctionModel:
    return FunctionModel(meter.wrap(model.function), model_name=model.model_name)  # type: ignore[arg-type]


async def measure() -> dict[str, Any]:
    intake_meter, skeleton_meter, module_meter, docs_meter = Meter(), Meter(), Meter(), Meter()
    pipeline = Pipeline(
        Settings(llm_mode="test"),
        cast(Models, None),  # unused: both stage models are given
        SPECIES,
        intake_model=_metered(offline.intake_model(), intake_meter),
        skeleton_model=_metered(offline.skeleton_model(), skeleton_meter),
        module_model=_metered(offline.module_model(), module_meter),
        docs_model=_metered(offline.docs_model(), docs_meter),
    )

    spec = Spec(description=DESCRIPTION)
    assert open_questions(spec, SPECIES)
    result = await pipeline.intake(spec)
    planned = await pipeline.skeleton(result.spec)
    built = await pipeline.modules(result.spec, planned.skeleton)
    await pipeline.document(result.spec, planned.skeleton, built)
    return {
        "intake": intake_meter.totals(),
        "skeleton": skeleton_meter.totals(),
        "modules": module_meter.totals(),
        "docs": docs_meter.totals(),
    }


def main() -> None:
    import json

    print(json.dumps(asyncio.run(measure()), indent=2))


if __name__ == "__main__":
    main()
