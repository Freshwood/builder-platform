"""Token budget of the pipeline stages, measured offline (see modules/pipeline/bench.py).

The request side is exact (instructions, output schema, prompt; for modules also the catalog digest). Compare: the old single design
call carried a 7.6K-token prefix on every request (docs/ai/benchmarks). Tighten the limits when a
change makes the stages smaller.
"""

import asyncio
from typing import Any

import pytest

from homeworking.modules.pipeline.bench import measure

# stage -> (max input tokens of one request, max static prefix tokens)
BUDGET = {
    "intake": (900, 800),
    "skeleton": (1_800, 1_700),
    "modules": (3_400, 2_800),
    "docs": (900, 700),
}


@pytest.fixture(scope="module")
def bench() -> dict[str, Any]:
    return asyncio.run(measure())


@pytest.mark.parametrize("stage", BUDGET)
def test_stage_stays_within_budget(bench: dict[str, Any], stage: str) -> None:
    request_limit, prefix_limit = BUDGET[stage]
    assert bench[stage]["max_request_input_tokens"] <= request_limit
    assert bench[stage]["prefix_tokens_per_request"] <= prefix_limit
    assert bench[stage]["stable_prefix"]
