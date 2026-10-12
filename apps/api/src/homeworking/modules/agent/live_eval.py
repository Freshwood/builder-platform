"""Live evaluation of the agent against the regression briefs (``task eval:live``). Never in CI.

``task bench`` measures tokens offline and the regression cases prove offline that the engine and
the tools behave. Neither can tell whether a REAL model solves a brief. This harness sends every
brief of ``apps/api/tests/regressions/<slug>/case.json`` through the full agent path exactly like
``api/chat.py`` (routing, models, tools, engine, usage limits), k times, and checks the project
the agent ends with against the case's ``expect`` (``calc_engine.assembly.intent``).

    task eval:live -- --label solar-v1 --runs 3 --yes
    task eval:live -- --dry-run                      # what would run, worst-case cost
    task eval:live -- --compare old.json new.json    # did a prompt or model change help?

Real model calls cost money. The harness refuses to run in ``LLM_MODE=test`` (use
``--allow-offline`` for a self-test with the offline model) and asks for ``--yes`` (or
``LIVE_EVAL_YES=1``) before it talks to a provider. Runs are stored in a throw-away SQLite
database; nothing is written to ``agent_runs``. See ``docs/ai/EVALS.md``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

from calc_engine.assembly.intent import Expectation, evaluate, view_consistency
from homeworking.bootstrap import Container, build_container
from homeworking.modules.agent.prompts import PROMPT_VERSION
from homeworking.modules.agent.provenance import prompt_fingerprint
from homeworking.modules.agent.routing import ROUTING_VERSION, Role, route
from homeworking.modules.agent.tools import AgentDeps
from homeworking.modules.compliance.redaction import redact
from homeworking.modules.compliance.safety import check_message
from homeworking.settings import Settings

SCHEMA_VERSION = 1
DEFAULT_CASES_DIR = Path("apps/api/tests/regressions")
DEFAULT_OUT_DIR = Path("docs/ai/evals")
DEFAULT_PRICES = Path("docs/ai/models.json")
DEFAULT_BUDGET_USD = 5.0
CONFIRM_ENV = "LIVE_EVAL_YES"
FINAL_TEXT_MAX_CHARS = 2000
ERROR_MAX_CHARS = 500
EXIT_REFUSED = 2

Prices = dict[str, dict[str, float]]


# --------------------------------------------------------------------------------------------
# Cases
# --------------------------------------------------------------------------------------------


class EvalCase(BaseModel):
    """The part of ``case.json`` the live eval needs; everything else is ignored on purpose.

    ``tests/regressions/loader.py`` is the authoritative, strict schema (and is tested offline).
    The harness must not import from ``tests/``, so it reads only these four fields.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    brief: str = Field(min_length=1)
    expect: Expectation
    failure_class: str = ""


class CaseLoadError(ValueError):
    """A case directory is missing, empty or malformed."""


def load_cases(directory: Path, only: Sequence[str] = ()) -> list[EvalCase]:
    """Every ``<slug>/case.json`` below ``directory`` (sorted), optionally filtered by slug."""
    if not directory.is_dir():
        raise CaseLoadError(f"{directory}: Verzeichnis nicht gefunden")
    cases: list[EvalCase] = []
    for sub in sorted(p for p in directory.iterdir() if p.is_dir()):
        file = sub / "case.json"
        if not file.is_file():
            continue
        try:
            case = EvalCase.model_validate(json.loads(file.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValidationError) as error:
            raise CaseLoadError(f"{file}: {error}") from error
        if case.id != sub.name:
            raise CaseLoadError(f"{file}: id '{case.id}' passt nicht zum Verzeichnis '{sub.name}'")
        cases.append(case)
    unknown = sorted(set(only) - {c.id for c in cases})
    if unknown:
        known = ", ".join(c.id for c in cases) or "none"
        raise CaseLoadError(f"Unknown case(s): {', '.join(unknown)} (known: {known})")
    if only:
        cases = [c for c in cases if c.id in only]
    if not cases:
        raise CaseLoadError(f"{directory}: no cases found")
    return cases


# --------------------------------------------------------------------------------------------
# Cost
# --------------------------------------------------------------------------------------------


def load_prices(path: Path) -> Prices:
    """USD per 1M tokens by model id from ``docs/ai/models.json``; empty when the file is absent."""
    if not path.is_file():
        return {}
    models = json.loads(path.read_text(encoding="utf-8")).get("models", {})
    return {str(name): dict(price) for name, price in models.items()}


def price_for(model_name: str, prices: Prices) -> dict[str, float] | None:
    """Price entry of a model: exact id, else the longest id that prefixes the name.

    Providers often answer with a dated variant (``vendor/model-20261001``); the prefix rule
    maps it to the listed model. Unknown models have no price (cost stays unknown).
    """
    wanted = model_name.lower()
    exact = {name.lower(): price for name, price in prices.items()}
    if wanted in exact:
        return exact[wanted]
    prefixes = [name for name in exact if wanted.startswith(name)]
    return exact[max(prefixes, key=len)] if prefixes else None


def request_cost_usd(request: dict[str, Any], price: dict[str, float]) -> float:
    """USD of one model request; cached input tokens are billed at the cache price.

    ``input_tokens`` of a provider response includes the cached part (pydantic-ai convention).
    A model without a ``cache_read`` price bills cached tokens like normal input.
    """
    input_tokens = int(request.get("input_tokens") or 0)
    cached = min(int(request.get("cache_read_tokens") or 0), input_tokens)
    output_tokens = int(request.get("output_tokens") or 0)
    cache_price = price.get("cache_read", price["input"])
    return (
        (input_tokens - cached) * price["input"]
        + cached * cache_price
        + output_tokens * price["output"]
    ) / 1_000_000


def run_cost_usd(
    requests: list[dict[str, Any]], fallback_model: str, prices: Prices
) -> tuple[float | None, int]:
    """Total USD of a run (None if no request could be priced) and the number of unpriced requests."""
    total, priced, unpriced = 0.0, 0, 0
    for request in requests:
        price = price_for(str(request.get("model") or fallback_model), prices) or price_for(
            fallback_model, prices
        )
        if price is None:
            unpriced += 1
            continue
        total += request_cost_usd(request, price)
        priced += 1
    return (round(total, 6) if priced else None), unpriced


def max_cost_usd(limits: UsageLimits, price: dict[str, float] | None) -> float | None:
    """Worst-case USD of one run: the token limit, every token at the dearer of the two prices.

    An upper bound: it ignores cache discounts and the one request that may cross the limit.
    """
    if price is None or limits.total_tokens_limit is None:
        return None
    return limits.total_tokens_limit * max(price["input"], price["output"]) / 1_000_000


# --------------------------------------------------------------------------------------------
# One run
# --------------------------------------------------------------------------------------------


@dataclass
class RunRecord:
    """Everything measured in one agent turn (one JSON object per run in the report)."""

    case: str
    run: int
    model_role: str
    routing_reason: str
    model: str
    accepted: bool = False
    success: bool = False
    attempts: int = 0
    rejected: int = 0
    outcomes: dict[str, int] = field(default_factory=dict)
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float | None = None
    unpriced_requests: int = 0
    duration_s: float = 0.0
    intent_violations: list[str] = field(default_factory=list)
    view_violations: list[str] = field(default_factory=list)
    final_text: str = ""
    error: str | None = None


async def run_case(
    container: Container,
    case: EvalCase,
    model: Model,
    *,
    run: int = 1,
    role: Role = "designer",
    routing_reason: str = "",
    limits: UsageLimits | None = None,
    prices: Prices | None = None,
) -> RunRecord:
    """One full agent turn for the brief, measured. ``model`` is injected (tests use scripted ones).

    Mirrors ``api/chat.py``: redaction and safety check of the user text, the container's agent
    with ``model`` as override, the configured usage limits, a fresh guest and no active project.
    Errors of the agent run (usage limit, provider error) are recorded, not raised.
    """
    settings = container.settings
    limits = limits or UsageLimits(
        request_limit=settings.agent_request_limit,
        total_tokens_limit=settings.agent_total_tokens_limit,
    )
    record = RunRecord(
        case=case.id,
        run=run,
        model_role=role,
        routing_reason=routing_reason,
        model=model.model_name,
    )
    text = redact(case.brief)
    verdict = check_message(text)
    if verdict.blocked:
        # Chat answers with a fixed referral and never calls the model; so does the eval.
        record.error = f"safety_gate: {verdict.topic}"
        record.final_text = verdict.response or ""
        return record

    owner = (await container.identity.create_guest()).id
    deps = AgentDeps(
        owner_id=owner, projects=container.projects, project_id=None, trace_id=f"eval-{case.id}"
    )
    started = time.perf_counter()
    try:
        result = await container.agent.run(text, model=model, deps=deps, usage_limits=limits)
        record.final_text = str(result.output)[:FINAL_TEXT_MAX_CHARS]
    except Exception as error:  # a failed run is a measurement, not a crash
        record.error = f"{type(error).__name__}: {error}"[:ERROR_MAX_CHARS]
    record.duration_s = round(time.perf_counter() - started, 3)

    record.attempts = len(deps.design_attempts)
    for attempt in deps.design_attempts:
        outcome = str(attempt.get("outcome"))
        record.outcomes[outcome] = record.outcomes.get(outcome, 0) + 1
        if not attempt.get("accepted"):
            record.rejected += 1
    record.requests = len(deps.requests)
    record.input_tokens = sum(int(r.get("input_tokens") or 0) for r in deps.requests)
    record.output_tokens = sum(int(r.get("output_tokens") or 0) for r in deps.requests)
    record.cache_read_tokens = sum(int(r.get("cache_read_tokens") or 0) for r in deps.requests)
    record.cost_usd, record.unpriced_requests = run_cost_usd(
        deps.requests, model.model_name, prices or {}
    )

    if deps.project_id is not None:
        try:
            project = await container.projects.get(owner, deps.project_id)
        except LookupError:
            project = None
        if project is not None:
            record.accepted = True
            record.intent_violations = await _checked(
                lambda: evaluate(project.inputs, project.result, case.expect, container.engine)
            )
            record.view_violations = await _checked(lambda: view_consistency(project.result))
    record.success = record.accepted and not record.intent_violations and record.error is None
    return record


async def _checked(check: Any) -> list[str]:
    """Violations as ``[rule] detail`` texts; a crashing check counts as a violation."""
    try:
        return [f"[{v.rule}] {v.detail}" for v in await asyncio.to_thread(check)]
    except Exception as error:
        return [f"[check_error] {type(error).__name__}: {error}"[:ERROR_MAX_CHARS]]


# --------------------------------------------------------------------------------------------
# Plan and aggregation
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannedRun:
    case: EvalCase
    run: int
    role: Role
    reason: str
    model_name: str


def role_models(settings: Settings) -> dict[Role, str]:
    """Configured model names by role (the fast role falls back to the designer)."""
    return {
        "designer": settings.llm_model or "homeworking-offline",
        "fast": settings.llm_model_fast or settings.llm_model or "homeworking-offline",
    }


def plan_runs(
    cases: Sequence[EvalCase], runs: int, settings: Settings, forced_role: Role | None
) -> list[PlannedRun]:
    """Case x run, with the role the router picks for a first message without a project."""
    names = role_models(settings)
    planned: list[PlannedRun] = []
    for case in cases:
        routed = route(case.brief, has_project=False)
        role: Role = forced_role or routed.role
        reason = "forced" if forced_role else routed.reason
        planned += [PlannedRun(case, i + 1, role, reason, names[role]) for i in range(runs)]
    return planned


def _mean(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def summarize(runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate run records (dicts as stored in the report) of one brief or of all briefs.

    * ``success``: engine result exists AND zero intent violations AND the run did not fail.
    * ``pass_at_1``: expected success probability of one run (successes / runs).
    * ``pass_any`` / ``pass_all``: at least one / every one of the k runs succeeded.
    """
    n = len(runs)
    successes = sum(1 for r in runs if r["success"])
    costs = [r["cost_usd"] for r in runs if r["cost_usd"] is not None]
    return {
        "runs": n,
        "successes": successes,
        "success_rate": round(successes / n, 3) if n else 0.0,
        "pass_at_1": round(successes / n, 3) if n else 0.0,
        "pass_any": successes > 0,
        "pass_all": n > 0 and successes == n,
        "accepted_runs": sum(1 for r in runs if r["accepted"]),
        "mean_attempts": _mean([r["attempts"] for r in runs]),
        "mean_rejected": _mean([r["rejected"] for r in runs]),
        "mean_requests": _mean([r["requests"] for r in runs]),
        "mean_duration_s": _mean([r["duration_s"] for r in runs]),
        "intent_violation_runs": sum(1 for r in runs if r["intent_violations"]),
        "view_violation_runs": sum(1 for r in runs if r["view_violations"]),
        "error_runs": sum(1 for r in runs if r["error"]),
        "input_tokens": sum(r["input_tokens"] for r in runs),
        "output_tokens": sum(r["output_tokens"] for r in runs),
        "cost_usd": round(sum(costs), 6) if costs else None,
        "mean_cost_usd": round(sum(costs) / len(costs), 6) if costs else None,
        "unpriced_requests": sum(r["unpriced_requests"] for r in runs),
    }


def build_report(
    *,
    label: str,
    records: Sequence[RunRecord],
    cases: Sequence[EvalCase],
    settings: dict[str, Any],
    prompt_version: str,
    fingerprint: str,
    aborted: str | None,
) -> dict[str, Any]:
    runs = [asdict(r) for r in records]
    per_case: dict[str, Any] = {}
    for case in cases:
        case_runs = [r for r in runs if r["case"] == case.id]
        if not case_runs:
            continue  # aborted before this brief started
        per_case[case.id] = {
            "failure_class": case.failure_class,
            "brief": case.brief,
            "summary": summarize(case_runs),
            "runs": case_runs,
        }
    overall = summarize(runs)
    summaries = [c["summary"] for c in per_case.values()]
    overall["cases"] = len(summaries)
    overall["cases_pass_all"] = sum(1 for s in summaries if s["pass_all"])
    overall["cases_pass_any"] = sum(1 for s in summaries if s["pass_any"])
    return {
        "schema_version": SCHEMA_VERSION,
        "label": label,
        "date": date.today().isoformat(),
        "prompt_version": prompt_version,
        "prompt_fingerprint": fingerprint,
        "routing_version": ROUTING_VERSION,
        "settings": settings,
        "aborted": aborted,
        "overall": overall,
        "cases": per_case,
    }


def _money(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def markdown(report: dict[str, Any]) -> str:
    s = report["settings"]
    overall = report["overall"]
    lines = [
        f"# Live eval: {report['label']}",
        "",
        f"- Date: {report['date']}",
        f"- Prompt: `{report['prompt_version']}` (fingerprint `{report['prompt_fingerprint']}`, "
        f"routing {report['routing_version']})",
        f"- Models: designer `{s['models']['designer']}`, fast `{s['models']['fast']}`"
        + (f", role forced to `{s['model_role']}`" if s["model_role"] else ", roles routed"),
        f"- Runs per brief: {s['runs']}, request limit {s['request_limit']}, "
        f"token limit {s['total_tokens_limit']}, temperature {s['temperature']}, "
        f"reasoning {s['reasoning']}" + (", OFFLINE model" if s["offline"] else ""),
    ]
    if report["aborted"]:
        lines.append(f"- **Aborted: {report['aborted']}** (results are partial)")
    lines += [
        "",
        f"Overall: **{overall['successes']}/{overall['runs']} runs succeeded "
        f"({overall['success_rate']:.0%})**, {overall['cases_pass_all']}/{overall['cases']} "
        f"briefs in every run, mean {overall['mean_attempts']} attempts "
        f"({overall['mean_rejected']} rejected), cost {_money(overall['cost_usd'])} USD.",
        "",
        "| Brief | Class | Success | Rate | pass any | pass all | Attempts | Rejected | Requests "
        "| Intent viol. | View viol. | Cost USD | Time s |",
        "|---|---|---:|---:|:-:|:-:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for slug, case in report["cases"].items():
        c = case["summary"]
        lines.append(
            f"| {slug} | {case['failure_class']} | {c['successes']}/{c['runs']} "
            f"| {c['success_rate']:.0%} | {'yes' if c['pass_any'] else 'no'} "
            f"| {'yes' if c['pass_all'] else 'no'} | {c['mean_attempts']} | {c['mean_rejected']} "
            f"| {c['mean_requests']} | {c['intent_violation_runs']} | {c['view_violation_runs']} "
            f"| {_money(c['cost_usd'])} | {c['mean_duration_s']} |"
        )
    failures = [
        (slug, r) for slug, c in report["cases"].items() for r in c["runs"] if not r["success"]
    ]
    if failures:
        lines += ["", "## Failed runs", ""]
        for slug, r in failures:
            lines.append(
                f"### {slug} run {r['run']} ({r['model']}, accepted: "
                f"{'yes' if r['accepted'] else 'no'}, attempts {r['attempts']}, outcomes "
                f"{json.dumps(r['outcomes'], ensure_ascii=False)})"
            )
            if r["error"]:
                lines.append(f"- Error: `{r['error']}`")
            lines += [f"- Intent: {v}" for v in r["intent_violations"]]
            lines += [f"- View: {v}" for v in r["view_violations"]]
            if r["final_text"]:
                lines.append(f"- Final text: {r['final_text'][:300]!r}")
            lines.append("")
    if overall["unpriced_requests"]:
        lines += [
            "",
            f"{overall['unpriced_requests']} request(s) ran on a model that is not in "
            "`docs/ai/models.json`: their cost is missing from the totals.",
        ]
    return "\n".join(lines).rstrip() + "\n"


def write_report(report: dict[str, Any], out_dir: Path) -> Path:
    """Write ``<date>-<label>.json`` and ``.md``; an existing report is never overwritten."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_dir / f"{report['date']}-{report['label']}"
    n = 1
    while stem.with_suffix(".json").exists() or stem.with_suffix(".md").exists():
        n += 1
        stem = out_dir / f"{report['date']}-{report['label']}-{n}"
    stem.with_suffix(".json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    stem.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    return stem.with_suffix(".json")


# --------------------------------------------------------------------------------------------
# Compare
# --------------------------------------------------------------------------------------------


def load_report(path: Path) -> dict[str, Any]:
    report: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if report.get("schema_version") != SCHEMA_VERSION or "cases" not in report:
        raise ValueError(f"{path}: not a live eval report (schema_version {SCHEMA_VERSION})")
    return report


def _delta(old: float | None, new: float | None) -> float | None:
    return None if old is None or new is None else round(new - old, 6)


def compare_reports(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Per-brief deltas and verdicts.

    ``broken``: the brief succeeded at least once before and never now. ``regressed``: the
    success rate dropped (but not to zero). ``improved``: it rose. With one run per brief these
    are coarse (a single flaky run flips a verdict); use ``--runs 3`` or more for decisions.
    """
    rows: list[dict[str, Any]] = []
    for slug in sorted(set(old["cases"]) & set(new["cases"])):
        o, n = old["cases"][slug]["summary"], new["cases"][slug]["summary"]
        if o["success_rate"] > 0 and n["success_rate"] == 0:
            verdict = "broken"
        elif n["success_rate"] < o["success_rate"]:
            verdict = "regressed"
        elif n["success_rate"] > o["success_rate"]:
            verdict = "improved"
        else:
            verdict = "same"
        rows.append(
            {
                "case": slug,
                "verdict": verdict,
                "runs": [o["runs"], n["runs"]],
                "success_rate": [o["success_rate"], n["success_rate"]],
                "success_rate_delta": _delta(o["success_rate"], n["success_rate"]),
                "mean_attempts": [o["mean_attempts"], n["mean_attempts"]],
                "mean_attempts_delta": _delta(o["mean_attempts"], n["mean_attempts"]),
                "mean_cost_usd": [o["mean_cost_usd"], n["mean_cost_usd"]],
                "mean_cost_usd_delta": _delta(o["mean_cost_usd"], n["mean_cost_usd"]),
            }
        )
    return {
        "old": {k: old.get(k) for k in ("label", "date", "prompt_version", "prompt_fingerprint")},
        "new": {k: new.get(k) for k in ("label", "date", "prompt_version", "prompt_fingerprint")},
        "models": [old["settings"]["models"], new["settings"]["models"]],
        "overall_success_rate": [old["overall"]["success_rate"], new["overall"]["success_rate"]],
        "only_in_old": sorted(set(old["cases"]) - set(new["cases"])),
        "only_in_new": sorted(set(new["cases"]) - set(old["cases"])),
        "rows": rows,
        "regressions": [r["case"] for r in rows if r["verdict"] in ("broken", "regressed")],
    }


def _num(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _signed(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:+.{digits}f}"


def format_compare(result: dict[str, Any]) -> str:
    o, n = result["old"], result["new"]
    lines = [
        f"old: {o['label']} ({o['date']}, prompt {o['prompt_version']}, {o['prompt_fingerprint']})",
        f"new: {n['label']} ({n['date']}, prompt {n['prompt_version']}, {n['prompt_fingerprint']})",
    ]
    if result["models"][0] != result["models"][1]:
        lines.append(f"models differ: {result['models'][0]} -> {result['models'][1]}")
    lines.append(
        f"overall success rate: {result['overall_success_rate'][0]:.0%} -> "
        f"{result['overall_success_rate'][1]:.0%}"
    )
    lines += [
        "",
        f"{'brief':<32} {'verdict':<10} {'success':>13} {'attempts':>16} {'cost USD/run':>22}",
    ]
    for r in result["rows"]:
        flag = {"broken": "BROKEN", "regressed": "REGRESSED", "improved": "improved"}.get(
            r["verdict"], "same"
        )
        lines.append(
            f"{r['case']:<32} {flag:<10} "
            f"{r['success_rate'][0]:>5.0%} -> {r['success_rate'][1]:<4.0%} "
            f"{_num(r['mean_attempts'][0], 1):>5} -> {_num(r['mean_attempts'][1], 1):<5}"
            f"({_signed(r['mean_attempts_delta'], 1)}) "
            f"{_num(r['mean_cost_usd'][0], 4):>7} -> {_num(r['mean_cost_usd'][1], 4):<7}"
            f"({_signed(r['mean_cost_usd_delta'], 4)})"
        )
    for slug in result["only_in_old"]:
        lines.append(f"{slug}: only in old report (not compared)")
    for slug in result["only_in_new"]:
        lines.append(f"{slug}: only in new report (not compared)")
    lines.append("")
    if result["regressions"]:
        lines.append("REGRESSIONS (passed before, worse now): " + ", ".join(result["regressions"]))
    else:
        lines.append("No regression.")
    runs = {tuple(r["runs"]) for r in result["rows"]}
    if any(1 in pair for pair in runs):
        lines.append("Note: a side with one run per brief is noisy; repeat with --runs 3 or more.")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Live evaluation of the agent against the regression briefs (costs money)."
    )
    parser.add_argument("--label", default="current", help="report name: <date>-<label>.json")
    parser.add_argument("--runs", type=int, default=1, help="runs per brief (default 1)")
    parser.add_argument("--case", action="append", default=[], help="only this slug (repeatable)")
    parser.add_argument(
        "--model-role",
        choices=["designer", "fast"],
        help="force this model role instead of the router's choice",
    )
    parser.add_argument("--cases-dir", type=Path, default=DEFAULT_CASES_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--prices", type=Path, default=DEFAULT_PRICES)
    parser.add_argument(
        "--budget-usd",
        type=float,
        default=DEFAULT_BUDGET_USD,
        help=f"stop starting new runs once this much was spent (default {DEFAULT_BUDGET_USD})",
    )
    parser.add_argument(
        "--yes", action="store_true", help=f"confirm real calls (or {CONFIRM_ENV}=1)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="list the plan and the worst-case cost"
    )
    parser.add_argument(
        "--allow-offline",
        action="store_true",
        help="allow LLM_MODE=test: runs the offline model (self-test, no cost)",
    )
    parser.add_argument(
        "--compare", nargs=2, metavar=("OLD", "NEW"), type=Path, help="compare two JSON reports"
    )
    return parser


def _refuse(message: str) -> int:
    print(f"live_eval: {message}", file=sys.stderr)
    return EXIT_REFUSED


def _limits(settings: Settings) -> UsageLimits:
    return UsageLimits(
        request_limit=settings.agent_request_limit,
        total_tokens_limit=settings.agent_total_tokens_limit,
    )


def _plan_text(planned: Sequence[PlannedRun], settings: Settings, prices: Prices) -> str:
    limits = _limits(settings)
    lines = [
        f"{len(planned)} run(s), request limit {settings.agent_request_limit}, token limit "
        f"{settings.agent_total_tokens_limit} per run, LLM_MODE={settings.llm_mode}",
        "",
        f"{'brief':<32} {'run':>3} {'role':<9} {'reason':<18} {'model':<28} {'max USD':>8}",
    ]
    total: float | None = 0.0
    for p in planned:
        worst = max_cost_usd(limits, price_for(p.model_name, prices))
        total = None if worst is None or total is None else total + worst
        lines.append(
            f"{p.case.id:<32} {p.run:>3} {p.role:<9} {p.reason:<18} {p.model_name:<28} "
            f"{_money(worst):>8}"
        )
    lines.append("")
    if total is None:
        lines.append(
            "Worst-case cost: unknown, a model is missing in the price list "
            "(docs/ai/models.json); only the token limit bounds the spend."
        )
    else:
        lines.append(
            f"Worst-case cost: {total:.2f} USD (every run at the token limit, all tokens at the "
            "dearer price). Typical runs cost a small fraction of that."
        )
    return "\n".join(lines)


def _settings_block(settings: Settings, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "llm_mode": settings.llm_mode,
        "offline": settings.llm_mode == "test",
        "models": role_models(settings),
        "model_role": args.model_role,
        "runs": args.runs,
        "request_limit": settings.agent_request_limit,
        "total_tokens_limit": settings.agent_total_tokens_limit,
        "temperature": settings.llm_temperature,
        "reasoning": settings.llm_reasoning,
        "max_output_tokens": settings.llm_max_output_tokens,
        "budget_usd": args.budget_usd,
    }


async def evaluate_all(
    container: Container,
    planned: Sequence[PlannedRun],
    prices: Prices,
    budget_usd: float,
) -> tuple[list[RunRecord], str | None]:
    """Run the plan one after another; stop early on the budget or on Ctrl-C."""
    records: list[RunRecord] = []
    spent = 0.0
    for p in planned:
        if spent >= budget_usd:
            return records, f"budget of {budget_usd:.2f} USD reached after {len(records)} run(s)"
        try:
            record = await run_case(
                container,
                p.case,
                container.models.for_role(p.role),
                run=p.run,
                role=p.role,
                routing_reason=p.reason,
                prices=prices,
            )
        except (KeyboardInterrupt, asyncio.CancelledError):
            return records, f"interrupted after {len(records)} run(s)"
        records.append(record)
        spent += record.cost_usd or 0.0
        print(
            f"[{len(records)}/{len(planned)}] {p.case.id} run {p.run}: "
            f"{'OK' if record.success else 'FAIL'} attempts={record.attempts} "
            f"rejected={record.rejected} requests={record.requests} "
            f"cost={_money(record.cost_usd)} USD {record.duration_s}s"
            + (f" error={record.error}" if record.error else "")
        )
    return records, None


async def _run_all(
    settings: Settings,
    planned: Sequence[PlannedRun],
    cases: Sequence[EvalCase],
    prices: Prices,
    args: argparse.Namespace,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        local = settings.model_copy(
            update={"database_url": f"sqlite+aiosqlite:///{Path(tmp) / 'live_eval.db'}"}
        )
        container = build_container(local)
        await container.create_schema()
        try:
            fingerprint = await prompt_fingerprint(container.engine)
            records, aborted = await evaluate_all(container, planned, prices, args.budget_usd)
        finally:
            await container.close()
    return build_report(
        label=args.label,
        records=records,
        cases=cases,
        settings=_settings_block(settings, args),
        prompt_version=PROMPT_VERSION,
        fingerprint=fingerprint,
        aborted=aborted,
    )


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    """CLI entry. Returns the exit code: 0 ok, 1 regressions found (compare), 2 refused."""
    args = _parser().parse_args(argv)
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

    if args.compare:
        try:
            result = compare_reports(*(load_report(p) for p in args.compare))
        except (OSError, ValueError, KeyError) as error:
            return _refuse(f"cannot compare: {error}")
        print(format_compare(result))
        return 1 if result["regressions"] else 0

    if args.runs < 1:
        return _refuse("--runs must be at least 1")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", args.label):
        return _refuse("--label may only contain letters, digits, '.', '_' and '-'")
    try:
        settings = settings or Settings()
        cases = load_cases(args.cases_dir, args.case)
    except (ValidationError, CaseLoadError) as error:
        return _refuse(str(error))

    offline = settings.llm_mode == "test"
    if offline and not args.allow_offline:
        return _refuse(
            "LLM_MODE=test: nothing real to evaluate. Set LLM_MODE=openai, LLM_MODEL and the API "
            "key in .env, or pass --allow-offline to self-test with the offline model."
        )

    prices = load_prices(args.prices)
    planned = plan_runs(cases, args.runs, settings, args.model_role)
    print(_plan_text(planned, settings, prices))
    if args.dry_run:
        return 0

    if not offline:
        print(
            f"\nWARNING: {len(planned)} agent run(s) will call the paid LLM provider "
            f"({settings.llm_base_url}). Stops at {args.budget_usd:.2f} USD actual spend.",
            file=sys.stderr,
        )
        if not (args.yes or os.environ.get(CONFIRM_ENV) == "1"):
            return _refuse(f"refusing to spend money without --yes (or {CONFIRM_ENV}=1)")

    report = asyncio.run(_run_all(settings, planned, cases, prices, args))
    path = write_report(report, args.out)
    print()
    print(markdown(report))
    print(f"Report: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
