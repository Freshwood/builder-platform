"""Token budget of the agent, measured offline (see devtools/homeworking_dev/bench.py).

The limits are the measured values of the current prompt version plus a small margin. A
prompt, tool or history change that makes requests bigger fails here; tighten the limits when
a change makes them smaller (and record the new numbers with `task bench`).
"""

import asyncio
from typing import Any

import pytest

from homeworking_dev.bench import run_bench

# scenario -> (max input tokens of the whole turn, max tokens of a single request)
# Baseline 2026-10-07.2 (docs/ai/benchmarks/2026-10-07-baseline.md) in the comments.
# Raised in 2026-10-08.1 (shapes, members, joints, buildings: +1.7K prefix tokens), tightened
# in 2026-10-14.1 (packs and templates removed: -1.6K prefix tokens), see
# docs/ai/PROMPT_CHANGELOG.md. Before 2026-10-14.1: pack_create 19_500/10_300, template_create
# 19_500/10_200, 60_000/13_600, 21_500/11_100, 23_000/11_900 and a 9_200 prefix.
# Raised in 2026-10-28.4 (plan_design for new designs: +0.8K prefix tokens, save_design stays for
# rebuilds), plan_create added; see docs/ai/PROMPT_CHANGELOG.md.
BUDGET = {
    "design_create": (18_600, 10_100),
    "plan_create": (17_500, 9_200),
    "free_design": (53_000, 11_900),
    "followup_1": (19_600, 10_200),
    "followup_2": (21_100, 11_000),
}
MAX_PREFIX_TOKENS = 8_500


@pytest.fixture(scope="module")
def bench() -> dict[str, Any]:
    return asyncio.run(run_bench())


@pytest.mark.parametrize("scenario", BUDGET)
def test_scenario_stays_within_budget(bench: dict[str, Any], scenario: str) -> None:
    turn_limit, request_limit = BUDGET[scenario]
    result = bench[scenario]
    assert result["input_tokens"] <= turn_limit
    assert result["max_request_input_tokens"] <= request_limit


def test_static_prefix_is_small_and_stable(bench: dict[str, Any]) -> None:
    prefix = bench["prefix"]
    assert prefix["instructions"] + prefix["tools_total"] <= MAX_PREFIX_TOKENS
    # A byte-identical prefix on every request is what provider prompt caching needs.
    assert all(bench[s]["stable_prefix"] for s in BUDGET)


def test_free_design_needs_two_repairs(bench: dict[str, Any]) -> None:
    """Guards the scenario itself: the scripted broken designs must really be rejected."""
    assert bench["free_design"]["design_attempts"] == [False, False, True]
