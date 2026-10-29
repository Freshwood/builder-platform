"""Run one brief through the pipeline stages with the real models (``task pipeline:live``).

The chat agent is left out on purpose: this shows what the stages themselves cost and where they
fail (tokens, requests, repair rounds and the engine's objections per stage), without the noise of
the chat model's own turns. Costs money and needs a key; never in CI.

    task pipeline:live -- --case tonie_cloud_shelf
    task pipeline:live -- --brief "Schrank 80 x 40 x 100 cm, innen" --timeout 600
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from homeworking.calc_engine.engine import default_engine
from homeworking.calc_engine.pipeline.budget import classify, time_budget_s
from homeworking.construction_model.pipeline import Spec
from homeworking.modules.agent.planner import CHAT_RESERVE_S
from homeworking.modules.llm.model import build_models
from homeworking.modules.pipeline.stages import (
    ModulesRejectedError,
    Pipeline,
    SkeletonRejectedError,
    StageFailedError,
    StageUsage,
)
from homeworking.settings import Settings

CASES = Path(__file__).resolve().parents[2] / "tests" / "regressions"


def _line(usage: StageUsage, error: str | None) -> str:
    status = "FAILED" if error else "ok"
    text = (
        f"{usage.stage:9} {status:6} {usage.requests:3} requests  "
        f"in {usage.input_tokens:7,}  out {usage.output_tokens:7,}  {usage.duration_ms / 1000:6.1f}s"
        f"  {usage.model}"
    )
    return text + (f"\n          {error[:700]}" if error else "")


async def run(brief: str, seconds: int, *, budgeted: bool) -> int:
    """The design stages as the chat starts them: no intake, the time budget of the category."""
    settings = Settings()
    engine = default_engine()
    species = {k: m.label for k, m in engine.catalog.lumber_species().items()}
    pipeline = Pipeline(settings, build_models(settings, stages=True), species, engine=engine)
    spec = Spec(description=brief)
    category = classify(spec)
    budget = time_budget_s(spec) - CHAT_RESERVE_S
    print(f"category {category}, budget {time_budget_s(spec)} s ({budget} s for the stages)")
    started = time.perf_counter()
    stages: list[StageUsage] = []

    async def seen(usage: StageUsage, error: str | None) -> None:
        stages.append(usage)
        print(_line(usage, error), flush=True)

    try:
        result = await asyncio.wait_for(
            pipeline.design(spec, on_stage=seen, budget_s=budget if budgeted else None), seconds
        )
    except (SkeletonRejectedError, ModulesRejectedError) as exc:
        print(f"\nREJECTED after {time.perf_counter() - started:.0f}s: {exc}"[:1500])
        return 1
    except StageFailedError as exc:
        print(f"\nFAILED after {time.perf_counter() - started:.0f}s: {exc}"[:1500])
        return 3
    except TimeoutError:
        print(f"\nTIMEOUT after {seconds}s")
        return 2
    elapsed = time.perf_counter() - started
    total_in = sum(s.input_tokens for s in stages)
    total_out = sum(s.output_tokens for s in stages)
    print(
        f"\naccepted: {len(result.design.parts)} parts, {len(result.design.steps)} steps, "
        f"explanation {'yes' if result.explanation else 'no'}"
    )
    print(f"total {total_in:,} in / {total_out:,} out tokens, {elapsed:.0f}s of {budget}s")
    return 0 if elapsed <= budget else 4


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="slug of a regression case (its brief is used)")
    parser.add_argument("--brief", help="free text brief")
    parser.add_argument("--timeout", type=int, default=900, help="hard stop in seconds")
    parser.add_argument(
        "--no-budget", action="store_true", help="measure without the category's time limit"
    )
    args = parser.parse_args()
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
    if args.case:
        brief = json.loads((CASES / args.case / "case.json").read_text(encoding="utf-8"))["brief"]
    elif args.brief:
        brief = args.brief
    else:
        parser.error("give --case or --brief")
    sys.exit(asyncio.run(run(brief, args.timeout, budgeted=not args.no_budget)))


if __name__ == "__main__":
    main()
