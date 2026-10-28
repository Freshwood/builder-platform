"""The live evaluation harness (``homeworking.modules.agent.live_eval``), tested offline.

No real model is involved: a scripted ``FunctionModel`` replays the recorded tool calls of the
podium regression case (``regressions/podium_kids_catwalk``). The tests prove the metrics, the
report files, the guards against accidental spend and the compare mode. Whether a real model
solves the briefs cannot be tested here; that is what ``task eval:live`` is for.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import UsageLimits

from calc_engine.assembly.intent import Expectation
from homeworking.bootstrap import Container, build_container
from homeworking.modules.agent import live_eval
from homeworking.modules.agent.live_eval import (
    CaseLoadError,
    EvalCase,
    RunRecord,
    build_report,
    compare_reports,
    load_cases,
    main,
    max_cost_usd,
    price_for,
    request_cost_usd,
    run_case,
    summarize,
    write_report,
)
from homeworking.modules.agent.model import Models
from homeworking.settings import Settings

REGRESSIONS = Path(__file__).resolve().parent / "regressions"
PODIUM = "podium_kids_catwalk"
MODEL_NAME = "vendor/scripted-model"
PRICES = {MODEL_NAME: {"input": 1.0, "output": 4.0, "cache_read": 0.1}}
FINAL = "Das Podest ist geplant."

Script = list[tuple[str, dict[str, Any]]]


def _attempt_args(number: int) -> dict[str, Any]:
    entry = json.loads(
        (REGRESSIONS / PODIUM / "attempts" / f"{number:02d}.json").read_text("utf-8")
    )
    args: dict[str, Any] = entry["raw_args"]
    return args


def golden_args() -> dict[str, Any]:
    """save_design arguments of the hand-fixed golden podium (design and params of the case)."""
    case = json.loads((REGRESSIONS / PODIUM / "case.json").read_text("utf-8"))
    design = json.loads((REGRESSIONS / PODIUM / "golden.json").read_text("utf-8"))
    return {"title": "Podest", "design": design, "params": case["golden"]["params"]}


def scripted(calls: Script) -> FunctionModel:
    """A model that sends ``calls`` one per request, then answers with text."""

    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        sent = sum(isinstance(m, ModelResponse) for m in messages)
        if sent < len(calls):
            name, args = calls[sent]
            return ModelResponse(parts=[ToolCallPart(name, args, tool_call_id=f"call_{sent}")])
        return ModelResponse(parts=[TextPart(FINAL)])

    return FunctionModel(respond, model_name=MODEL_NAME)


def podium_case(**envelope_overrides: Any) -> EvalCase:
    """The podium case; ``envelope_overrides`` tighten its envelope (e.g. ``max_length_mm=500``)."""
    case = load_cases(REGRESSIONS, [PODIUM])[0]
    if not envelope_overrides:
        return case
    raw = json.loads((REGRESSIONS / PODIUM / "case.json").read_text("utf-8"))["expect"]
    raw["envelope"] = {**raw.get("envelope", {}), **envelope_overrides}
    return case.model_copy(update={"expect": Expectation.model_validate(raw)})


@pytest.fixture
async def container(settings: Settings) -> AsyncIterator[Container]:
    box = build_container(settings)
    await box.create_schema()
    try:
        yield box
    finally:
        await box.close()


# --------------------------------------------------------------------------------------------
# run_case: metrics
# --------------------------------------------------------------------------------------------


async def test_accepted_design_meeting_the_intent_is_a_success(container: Container) -> None:
    model = scripted([("save_design", golden_args())])
    record = await run_case(container, podium_case(), model, prices=PRICES)

    assert record.accepted
    assert record.success
    assert record.intent_violations == []
    assert record.view_violations == []
    assert record.error is None
    assert (record.attempts, record.rejected) == (1, 0)
    assert record.outcomes == {"accepted": 1}
    assert record.requests == 2  # the tool call and the final answer
    assert record.input_tokens > 0
    assert record.output_tokens > 0
    assert record.final_text == FINAL
    assert record.model == MODEL_NAME
    assert record.cost_usd is not None
    assert record.cost_usd > 0
    assert record.duration_s >= 0


async def test_rejected_attempts_are_counted_and_the_run_still_succeeds(
    container: Container,
) -> None:
    # Attempt 02 of the case: an undeclared name in a when condition, rejected by the engine.
    model = scripted([("save_design", _attempt_args(2)), ("save_design", golden_args())])
    record = await run_case(container, podium_case(), model, prices=PRICES)

    assert record.success
    assert (record.attempts, record.rejected) == (2, 1)
    assert record.outcomes == {"engine_rejected": 1, "accepted": 1}
    assert record.requests == 3


async def test_intent_violation_makes_an_accepted_design_a_failure(container: Container) -> None:
    # The design is valid and builds, but the expectation demands a shorter podium than it is.
    model = scripted([("save_design", golden_args())])
    record = await run_case(container, podium_case(max_length_mm=500), model, prices=PRICES)
    assert record.accepted
    assert not record.success
    assert any("envelope" in v for v in record.intent_violations)

    # Recorded attempt 03 is accepted by the engine, but has no choice parameter 'surface'.
    model = scripted([("save_design", _attempt_args(3))])
    record = await run_case(container, podium_case(), model, prices=PRICES)

    assert record.accepted
    assert not record.success
    assert record.intent_violations
    assert any("choice_param" in v for v in record.intent_violations)
    assert record.rejected == 0


async def test_no_project_is_not_accepted(container: Container) -> None:
    record = await run_case(container, podium_case(), scripted([]), prices=PRICES)

    assert not record.accepted
    assert not record.success
    assert record.intent_violations == []
    assert record.attempts == 0
    assert record.final_text == FINAL


async def test_a_crashing_model_is_recorded_not_raised(container: Container) -> None:
    def boom(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise RuntimeError("provider down")

    record = await run_case(container, podium_case(), FunctionModel(boom, model_name=MODEL_NAME))

    assert not record.success
    assert record.error is not None
    assert "provider down" in record.error


async def test_usage_limit_ends_the_run_with_an_error(container: Container) -> None:
    model = scripted([("save_design", golden_args())])
    record = await run_case(
        container, podium_case(), model, limits=UsageLimits(request_limit=1), prices=PRICES
    )

    assert record.error is not None
    assert "UsageLimitExceeded" in record.error
    assert not record.success


async def test_unpriced_model_has_no_cost(container: Container) -> None:
    model = scripted([("save_design", golden_args())])
    record = await run_case(container, podium_case(), model, prices={})

    assert record.success
    assert record.cost_usd is None
    assert record.unpriced_requests == record.requests


async def test_blocked_brief_never_reaches_the_model(container: Container) -> None:
    def must_not_run(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise AssertionError("the safety gate should answer")

    case = podium_case().model_copy(update={"brief": "Ich will eine tragende Wand entfernen"})
    record = await run_case(container, case, FunctionModel(must_not_run))

    assert record.error is not None
    assert record.error.startswith("safety_gate")
    assert record.requests == 0
    assert not record.success


# --------------------------------------------------------------------------------------------
# Cases, cost, aggregation
# --------------------------------------------------------------------------------------------


def test_load_cases_reads_brief_and_expect_of_every_case() -> None:
    cases = load_cases(REGRESSIONS)

    assert PODIUM in {c.id for c in cases}
    podium = next(c for c in cases if c.id == PODIUM)
    assert podium.brief.startswith("Erstelle mir ein Podest")
    assert podium.failure_class == "engine_loop"
    assert podium.expect.envelope is not None
    assert podium.expect.envelope.max_length_mm == 2000


def test_load_cases_filters_by_slug_and_rejects_unknown_ones() -> None:
    assert [c.id for c in load_cases(REGRESSIONS, [PODIUM])] == [PODIUM]
    with pytest.raises(CaseLoadError, match="does_not_exist"):
        load_cases(REGRESSIONS, ["does_not_exist"])
    with pytest.raises(CaseLoadError):
        load_cases(REGRESSIONS / "nowhere")


def test_load_cases_rejects_an_id_that_differs_from_the_directory(tmp_path: Path) -> None:
    (tmp_path / "one").mkdir()
    (tmp_path / "one" / "case.json").write_text(
        json.dumps({"id": "two", "brief": "x", "expect": {}}), encoding="utf-8"
    )
    with pytest.raises(CaseLoadError, match="passt nicht"):
        load_cases(tmp_path)


def test_price_lookup_takes_exact_ids_and_dated_variants() -> None:
    prices = {
        "vendor/a": {"input": 1.0, "output": 2.0},
        "vendor/a-pro": {"input": 5.0, "output": 6.0},
    }

    assert price_for("vendor/a", prices) == prices["vendor/a"]
    assert price_for("Vendor/A-20261001", prices) == prices["vendor/a"]
    assert price_for("vendor/a-pro-20261001", prices) == prices["vendor/a-pro"]
    assert price_for("other/model", prices) is None


def test_request_cost_bills_cached_tokens_at_the_cache_price() -> None:
    price = {"input": 1.0, "output": 4.0, "cache_read": 0.1}
    request = {"input_tokens": 1_000_000, "cache_read_tokens": 800_000, "output_tokens": 100_000}

    # 200k fresh input * 1 + 800k cached * 0.1 + 100k output * 4, per million tokens
    assert request_cost_usd(request, price) == pytest.approx(0.2 + 0.08 + 0.4)
    no_cache_price = {"input": 1.0, "output": 4.0}
    assert request_cost_usd(request, no_cache_price) == pytest.approx(1.0 + 0.4)


def test_worst_case_cost_uses_the_token_limit_and_the_dearer_price() -> None:
    limits = UsageLimits(request_limit=12, total_tokens_limit=200_000)

    assert max_cost_usd(limits, {"input": 1.0, "output": 4.0}) == pytest.approx(0.8)
    assert max_cost_usd(limits, None) is None
    assert max_cost_usd(UsageLimits(request_limit=3), {"input": 1.0, "output": 4.0}) is None


def _run(
    case: str, run: int, *, success: bool, attempts: int = 1, cost: float | None = 0.01
) -> dict[str, Any]:
    from dataclasses import asdict

    return asdict(
        RunRecord(
            case=case,
            run=run,
            model_role="designer",
            routing_reason="default",
            model=MODEL_NAME,
            accepted=success,
            success=success,
            attempts=attempts,
            rejected=attempts - 1 if success else attempts,
            requests=attempts + 1,
            input_tokens=1000,
            output_tokens=100,
            cost_usd=cost,
            intent_violations=[] if success else ["[envelope] zu lang"],
            duration_s=2.0,
        )
    )


def test_summary_reports_rates_means_and_pass_numbers() -> None:
    runs = [
        _run("a", 1, success=True, attempts=1),
        _run("a", 2, success=False, attempts=3),
        _run("a", 3, success=True, attempts=2, cost=None),
    ]
    s = summarize(runs)

    assert (s["runs"], s["successes"]) == (3, 2)
    assert s["success_rate"] == pytest.approx(0.667, abs=1e-3)
    assert s["pass_at_1"] == s["success_rate"]
    assert s["pass_any"] is True
    assert s["pass_all"] is False
    assert s["mean_attempts"] == 2.0
    assert s["intent_violation_runs"] == 1
    assert s["cost_usd"] == pytest.approx(0.02)  # the unpriced run is left out
    assert summarize([_run("a", 1, success=False)])["pass_any"] is False


# --------------------------------------------------------------------------------------------
# Report files
# --------------------------------------------------------------------------------------------

SETTINGS_BLOCK = {
    "llm_mode": "openai",
    "offline": False,
    "models": {"designer": "vendor/d", "fast": "vendor/f"},
    "model_role": None,
    "runs": 2,
    "request_limit": 12,
    "total_tokens_limit": 200_000,
    "temperature": 0.2,
    "reasoning": "low",
    "max_output_tokens": 12_000,
    "budget_usd": 5.0,
}


def report_of(label: str, outcomes: dict[str, list[bool]]) -> dict[str, Any]:
    """A report whose briefs have the given per-run success flags."""
    records = [
        RunRecord(**{k: v for k, v in _run(slug, i + 1, success=ok).items()})
        for slug, flags in outcomes.items()
        for i, ok in enumerate(flags)
    ]
    cases = [
        EvalCase(id=slug, brief="x", expect=Expectation(), failure_class="engine_loop")
        for slug in outcomes
    ]
    return build_report(
        label=label,
        records=records,
        cases=cases,
        settings=SETTINGS_BLOCK,
        prompt_version="2026-10-10.1",
        fingerprint="abc123",
        aborted=None,
    )


def test_report_json_has_the_documented_schema(tmp_path: Path) -> None:
    report = report_of("schema", {"a": [True, False], "b": [True, True]})
    path = write_report(report, tmp_path / "evals")
    loaded = json.loads(path.read_text(encoding="utf-8"))

    assert path.parent == tmp_path / "evals"
    assert path.name.endswith("-schema.json")
    assert path.with_suffix(".md").is_file()
    assert set(loaded) == {
        "schema_version",
        "label",
        "date",
        "prompt_version",
        "prompt_fingerprint",
        "routing_version",
        "settings",
        "aborted",
        "overall",
        "cases",
    }
    assert loaded["schema_version"] == 1
    assert loaded["prompt_fingerprint"] == "abc123"
    assert set(loaded["settings"]) == set(SETTINGS_BLOCK)
    assert loaded["overall"]["runs"] == 4
    assert loaded["overall"]["successes"] == 3
    assert loaded["overall"]["cases_pass_all"] == 1
    assert loaded["overall"]["cases_pass_any"] == 2
    case = loaded["cases"]["a"]
    assert set(case) == {"failure_class", "brief", "summary", "runs"}
    assert len(case["runs"]) == 2
    run_keys = {
        "case", "run", "model_role", "routing_reason", "model", "accepted", "success", "attempts",
        "rejected", "outcomes", "requests", "input_tokens", "output_tokens", "cache_read_tokens",
        "stages", "stage_input_tokens", "stage_output_tokens",
            "cost_usd", "unpriced_requests", "duration_s", "intent_violations", "view_violations",
        "final_text", "error",
    }  # fmt: skip
    assert set(case["runs"][0]) == run_keys


def test_markdown_lists_failed_runs_with_their_violations(tmp_path: Path) -> None:
    path = write_report(report_of("md", {"a": [True, False]}), tmp_path)
    text = path.with_suffix(".md").read_text(encoding="utf-8")

    assert "# Live eval: md" in text
    assert "`2026-10-10.1`" in text
    assert "| a | engine_loop | 1/2 | 50% |" in text
    assert "## Failed runs" in text
    assert "[envelope] zu lang" in text


def test_an_existing_report_is_never_overwritten(tmp_path: Path) -> None:
    report = report_of("same", {"a": [True]})
    first = write_report(report, tmp_path)
    second = write_report(report, tmp_path)

    assert first != second
    assert second.name.endswith("-same-2.json")
    assert first.is_file()


# --------------------------------------------------------------------------------------------
# Compare mode
# --------------------------------------------------------------------------------------------


def test_compare_flags_a_brief_that_passed_before_and_fails_now() -> None:
    old = report_of(
        "old", {"a": [True, True], "b": [True, False], "c": [False, False], "d": [True]}
    )
    new = report_of(
        "new", {"a": [False, False], "b": [True, True], "c": [False, False], "e": [True]}
    )
    result = compare_reports(old, new)
    verdicts = {r["case"]: r["verdict"] for r in result["rows"]}

    assert verdicts == {"a": "broken", "b": "improved", "c": "same"}
    assert result["regressions"] == ["a"]
    assert result["only_in_old"] == ["d"]
    assert result["only_in_new"] == ["e"]
    row_a = next(r for r in result["rows"] if r["case"] == "a")
    assert row_a["success_rate"] == [1.0, 0.0]
    assert row_a["success_rate_delta"] == -1.0


def test_compare_marks_a_drop_that_is_not_a_total_failure_as_regressed() -> None:
    old = report_of("old", {"a": [True, True]})
    new = report_of("new", {"a": [True, False]})

    result = compare_reports(old, new)

    assert result["rows"][0]["verdict"] == "regressed"
    assert result["regressions"] == ["a"]


def test_compare_cli_prints_deltas_and_exits_1_on_regression(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = write_report(report_of("old", {"a": [True], "b": [True]}), tmp_path)
    new = write_report(report_of("new", {"a": [False], "b": [True]}), tmp_path)

    code = main(["--compare", str(old), str(new)])
    out = capsys.readouterr().out

    assert code == 1
    assert "BROKEN" in out
    assert "REGRESSIONS" in out
    assert "a" in out.split("REGRESSIONS")[1]
    assert main(["--compare", str(old), str(old)]) == 0
    assert "No regression." in capsys.readouterr().out


def test_compare_cli_rejects_files_that_are_not_reports(tmp_path: Path) -> None:
    junk = tmp_path / "junk.json"
    junk.write_text("{}", encoding="utf-8")

    assert main(["--compare", str(junk), str(junk)]) == live_eval.EXIT_REFUSED


# --------------------------------------------------------------------------------------------
# CLI guards
# --------------------------------------------------------------------------------------------


@pytest.fixture
def live_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'x.db'}",
        llm_mode="openai",
        llm_model=MODEL_NAME,
        llm_model_fast=MODEL_NAME,
    )


@pytest.fixture
def prices_file(tmp_path: Path) -> Path:
    path = tmp_path / "models.json"
    path.write_text(json.dumps({"models": PRICES}), encoding="utf-8")
    return path


@pytest.fixture
def no_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if a guard lets the harness reach the container (and so a provider)."""

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the harness must not build a container before the guards pass")

    monkeypatch.setattr(live_eval, "build_container", forbidden)
    monkeypatch.delenv(live_eval.CONFIRM_ENV, raising=False)


def common(tmp_path: Path, prices_file: Path, *extra: str) -> list[str]:
    return [
        "--cases-dir", str(REGRESSIONS),
        "--out", str(tmp_path / "evals"),
        "--prices", str(prices_file),
        *extra,
    ]  # fmt: skip


def test_refuses_in_test_mode_without_allow_offline(
    tmp_path: Path, settings: Settings, prices_file: Path, no_calls: None,
    capsys: pytest.CaptureFixture[str],
) -> None:  # fmt: skip
    code = main(common(tmp_path, prices_file, "--yes"), settings=settings)

    assert code == live_eval.EXIT_REFUSED
    assert "LLM_MODE=test" in capsys.readouterr().err
    assert not (tmp_path / "evals").exists()


def test_refuses_real_calls_without_yes(
    tmp_path: Path, live_settings: Settings, prices_file: Path, no_calls: None,
    capsys: pytest.CaptureFixture[str],
) -> None:  # fmt: skip
    code = main(common(tmp_path, prices_file, "--case", PODIUM), settings=live_settings)
    captured = capsys.readouterr()

    assert code == live_eval.EXIT_REFUSED
    assert "WARNING" in captured.err
    assert "--yes" in captured.err
    assert not (tmp_path / "evals").exists()


def test_yes_flag_or_env_var_lets_the_run_start(
    tmp_path: Path, live_settings: Settings, prices_file: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    started: list[int] = []

    async def fake_run_all(
        _settings: Settings, planned: Any, cases: Any, prices: Any, args: Any
    ) -> Any:
        started.append(len(planned))
        return build_report(
            label=args.label, records=[], cases=cases, settings=SETTINGS_BLOCK,
            prompt_version="v", fingerprint="f", aborted=None,
        )  # fmt: skip

    monkeypatch.setattr(live_eval, "_run_all", fake_run_all)
    monkeypatch.delenv(live_eval.CONFIRM_ENV, raising=False)
    args = common(tmp_path, prices_file, "--case", PODIUM, "--runs", "2")

    assert main([*args, "--yes"], settings=live_settings) == 0
    monkeypatch.setenv(live_eval.CONFIRM_ENV, "1")
    assert main(args, settings=live_settings) == 0
    assert started == [2, 2]


def test_dry_run_lists_the_plan_and_the_worst_case_cost_without_running(
    tmp_path: Path, live_settings: Settings, prices_file: Path, no_calls: None,
    capsys: pytest.CaptureFixture[str],
) -> None:  # fmt: skip
    code = main(
        common(tmp_path, prices_file, "--case", PODIUM, "--runs", "3", "--dry-run"),
        settings=live_settings,
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "3 run(s)" in out
    assert PODIUM in out
    assert MODEL_NAME in out
    # 3 runs * 200k tokens * 4 USD per million (the dearer output price)
    assert "Worst-case cost: 12.00 USD" in out
    assert not (tmp_path / "evals").exists()


def test_dry_run_says_so_when_a_model_has_no_price(
    tmp_path: Path, live_settings: Settings, no_calls: None, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        ["--cases-dir", str(REGRESSIONS), "--prices", str(tmp_path / "none.json"), "--dry-run"],
        settings=live_settings,
    )

    assert code == 0
    assert "Worst-case cost: unknown" in capsys.readouterr().out


def test_forced_model_role_overrides_the_router(
    tmp_path: Path, live_settings: Settings, prices_file: Path, no_calls: None,
    capsys: pytest.CaptureFixture[str],
) -> None:  # fmt: skip
    main(
        common(tmp_path, prices_file, "--case", PODIUM, "--model-role", "fast", "--dry-run"),
        settings=live_settings,
    )

    assert "forced" in capsys.readouterr().out


def test_bad_arguments_are_refused(
    tmp_path: Path, live_settings: Settings, prices_file: Path, no_calls: None
) -> None:
    base = common(tmp_path, prices_file, "--dry-run")

    assert main([*base, "--runs", "0"], settings=live_settings) == live_eval.EXIT_REFUSED
    assert main([*base, "--label", "../x"], settings=live_settings) == live_eval.EXIT_REFUSED
    assert main([*base, "--case", "nope"], settings=live_settings) == live_eval.EXIT_REFUSED


def test_offline_self_test_runs_end_to_end_and_writes_the_report(
    tmp_path: Path, settings: Settings, prices_file: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:  # fmt: skip
    monkeypatch.delenv(live_eval.CONFIRM_ENV, raising=False)
    cases = tmp_path / "cases"
    (cases / "shelf_offline").mkdir(parents=True)
    (cases / "shelf_offline" / "case.json").write_text(
        json.dumps(
            {
                "id": "shelf_offline",
                "brief": "Regal 80 × 30 × 180 cm",
                "failure_class": "intent_mismatch",
                "expect": {"envelope": {"max_height_mm": 2000}},
            }
        ),
        encoding="utf-8",
    )

    code = main(
        ["--cases-dir", str(cases), "--out", str(tmp_path / "evals"), "--prices",
         str(prices_file), "--allow-offline", "--runs", "2", "--label", "selftest"],
        settings=settings,
    )  # fmt: skip
    capsys.readouterr()

    assert code == 0
    [json_file] = (tmp_path / "evals").glob("*-selftest.json")
    report = json.loads(json_file.read_text(encoding="utf-8"))
    assert report["settings"]["offline"] is True
    assert report["overall"]["runs"] == 2
    assert report["overall"]["successes"] == 2
    assert report["cases"]["shelf_offline"]["summary"]["pass_all"] is True
    assert report["prompt_fingerprint"]
    assert json_file.with_suffix(".md").is_file()


async def test_the_budget_stops_further_runs(container: Container) -> None:
    case = podium_case()
    planned = [
        live_eval.PlannedRun(case, i + 1, "designer", "default", MODEL_NAME) for i in range(3)
    ]

    model = scripted([("save_design", golden_args())])
    scripted_container = replace(container, models=Models(designer=model, fast=model))

    prices = {MODEL_NAME: {"input": 1_000_000.0, "output": 1_000_000.0}}
    records, aborted = await live_eval.evaluate_all(scripted_container, planned, prices, 0.5)

    assert len(records) == 1
    assert aborted is not None
    assert "budget" in aborted
