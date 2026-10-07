"""Token budget of the agent, measured offline (see modules/agent/bench.py).

The limits are the measured values of the current prompt version plus a small margin. A
prompt, tool or history change that makes requests bigger fails here; tighten the limits when
a change makes them smaller (and record the new numbers with `task bench`).
"""

import asyncio
from typing import Any

import pytest

from homeworking.modules.agent.bench import run_bench

# scenario -> (max input tokens of the whole turn, max tokens of a single request)
# Baseline 2026-10-07.2 (docs/ai/benchmarks/2026-10-07-baseline.md) in the comments.
BUDGET = {
    "pack_create": (16_000, 8_500),  # was 25_187 / 13_337
    "template_create": (16_000, 8_500),  # was 24_917 / 13_071
    "free_design": (50_000, 11_500),  # was 79_728 / 19_345
    "followup_1": (18_000, 9_300),  # was 39_998 / 20_547
    "followup_2": (19_500, 10_000),  # was 42_239 / 21_668
}
MAX_PREFIX_TOKENS = 7_500  # was 11_839


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
