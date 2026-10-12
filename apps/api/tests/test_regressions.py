"""Replay of the regression cases in ``regressions/<slug>/`` (format: regressions/README.md).

Every case is checked twice, offline (no network, no LLM):

1. Each recorded tool call is replayed through the real agent tool path with a scripted
   ``FunctionModel``. The new outcome must equal ``expect_outcome`` and the error text the model
   would see must contain ``errors_contain``: the message stays actionable.
2. The golden design (the fix a human would make) must build and pass the corpus invariants, the
   case's intent expectation and the view consistency check.
"""

from __future__ import annotations

import json
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

# --import-mode=importlib adds neither the case loader nor the corpus to sys.path.
_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent / "regressions"))
sys.path.insert(0, str(_ROOT / "packages" / "calc-engine" / "tests"))

import loader  # noqa: E402
from corpus import Case, build_result, check  # noqa: E402
from loader import AttemptRecord, CaseError, LoadedCase, load_case  # noqa: E402

from calc_engine.assembly.intent import evaluate, view_consistency  # noqa: E402
from calc_engine.assembly.templates import templates  # noqa: E402
from calc_engine.engine import default_engine  # noqa: E402
from construction_model.assembly import AssemblyDesign  # noqa: E402
from construction_model.model import ProjectInputs  # noqa: E402
from homeworking.bootstrap import build_container  # noqa: E402
from homeworking.modules.agent.tools import AgentDeps, build_agent  # noqa: E402
from homeworking.settings import Settings  # noqa: E402

CASES = loader.load_all()
ENGINE = default_engine()


def _ids(cases: list[LoadedCase]) -> list[str]:
    return [c.slug for c in cases]


@asynccontextmanager
async def _run_calls(
    settings: Settings, calls: list[tuple[str, str | dict[str, Any]]]
) -> AsyncIterator[AgentDeps]:
    """Run an offline agent that sends ``calls`` one after another, then answers with text."""

    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        sent = sum(isinstance(m, ModelResponse) for m in messages)
        if sent < len(calls):
            name, args = calls[sent]
            return ModelResponse(parts=[ToolCallPart(name, args, tool_call_id=f"call_{sent}")])
        return ModelResponse(parts=[TextPart("Fertig.")])

    container = build_container(settings)
    await container.create_schema()
    try:
        owner = (await container.identity.create_guest()).id
        agent = build_agent(FunctionModel(respond), container.engine)
        deps = AgentDeps(owner_id=owner, projects=container.projects, project_id=None, trace_id="t")
        await agent.run("Regression", deps=deps)
        yield deps
    finally:
        await container.close()


async def replay(settings: Settings, attempts: list[AttemptRecord], index: int) -> dict[str, Any]:
    """Replay attempt ``index`` and return what the agent records for it now.

    Earlier accepted attempts run first (they create the project later calls act on); earlier
    failures are skipped, because every failed call of one tool counts against the agent's retry
    budget and none of them changes state.
    """
    calls = [
        (a.tool, a.raw_args)
        for a in attempts[:index]
        if a.outcome == "accepted" and a.raw_args is not None
    ]
    target = attempts[index]
    assert target.raw_args is not None, "ein Versuch ohne raw_args lässt sich nicht abspielen"
    calls.append((target.tool, target.raw_args))
    async with _run_calls(settings, calls) as deps:
        assert len(deps.design_attempts) == len(calls), deps.design_attempts
        return deps.design_attempts[-1]


def _attempt_params() -> list[Any]:
    params = []
    for case in CASES:
        for index, ref in enumerate(case.case.attempts):
            params.append(pytest.param(case, index, id=f"{case.slug}/{Path(ref.file).stem}"))
    return params


@pytest.mark.parametrize(("case", "index"), _attempt_params())
async def test_recorded_call_still_gets_the_recorded_outcome(
    settings: Settings, case: LoadedCase, index: int
) -> None:
    ref = case.case.attempts[index]
    entry = await replay(settings, case.attempts, index)
    assert entry["outcome"] == ref.expect_outcome, entry["errors"]
    text = "\n".join(entry["errors"])
    for needle in ref.errors_contain:
        assert needle in text, f"'{needle}' fehlt in den Fehlern:\n{text}"


def golden_design(case: LoadedCase) -> AssemblyDesign:
    golden = case.case.golden
    assert golden is not None
    if golden.template is not None:
        return templates()[golden.template].design
    assert case.golden_design is not None
    return AssemblyDesign.model_validate(case.golden_design)


@pytest.mark.parametrize(
    "case", [c for c in CASES if c.case.golden], ids=_ids([c for c in CASES if c.case.golden])
)
def test_golden_design_meets_the_invariants_and_the_intent(case: LoadedCase) -> None:
    golden = case.case.golden
    assert golden is not None
    design = golden_design(case)
    corpus_case = Case(
        f"regression:{case.slug}", design, dict(golden.params), source=f"regression:{case.slug}"
    )
    result = build_result(corpus_case, ENGINE)

    problems = [f"[{v.rule}] {v.detail}" for v in check(result, corpus_case)]
    inputs = ProjectInputs(
        title=case.case.title, pack_id="design", params=dict(golden.params), design=design
    )
    problems += [
        f"[{v.rule}] {v.detail}" for v in evaluate(inputs, result, case.case.expect, ENGINE)
    ]
    problems += [f"[{v.rule}] {v.detail}" for v in view_consistency(result)]
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------------------------
# The loader itself
# --------------------------------------------------------------------------------------------


def test_the_regression_cases_exist() -> None:
    assert {"podium_kids_catwalk", "tonie_cloud_shelf", "window_shutter_reported"} <= {
        c.slug for c in CASES
    }
    assert len({c.case.id for c in CASES}) == len(CASES)


def test_every_case_directory_has_a_case_file() -> None:
    for directory in loader.case_directories():
        assert (directory / "case.json").is_file(), f"{directory.name}: case.json fehlt"


def _write_case(root: Path, **changes: Any) -> Path:
    directory = root / "demo_case"
    (directory / "attempts").mkdir(parents=True)
    (directory / "attempts" / "01.json").write_text(
        json.dumps(
            {
                "tool": "save_design",
                "tool_call_id": "call_0",
                "outcome": "invalid_args",
                "accepted": False,
                "errors": ["design.explanation: Extra inputs are not permitted [extra_forbidden]"],
                "raw_args": {"title": "x", "design": {}},
                "design": None,
            }
        )
    )
    data: dict[str, Any] = {
        "id": "demo_case",
        "title": "Demo",
        "origin": {"kind": "hand_written", "ref": "test", "date": "2026-10-12"},
        "failure_class": "schema_validation",
        "brief": "Ein Regal",
        "expect": {"envelope": {"max_length_mm": 1000}},
        "attempts": [
            {
                "file": "attempts/01.json",
                "expect_outcome": "invalid_args",
                "errors_contain": ["explanation"],
            }
        ],
    }
    data.update(changes)
    (directory / "case.json").write_text(json.dumps(data))
    return directory


def test_a_wellformed_case_loads(tmp_path: Path) -> None:
    loaded = load_case(_write_case(tmp_path))
    assert loaded.case.attempts[0].synthetic is False
    assert loaded.attempts[0].tool == "save_design"


@pytest.mark.parametrize(
    "changes",
    [
        {"colour": "red"},
        {"origin": {"kind": "hand_written", "ref": "x", "date": "2026-10-12", "by": "me"}},
        {"origin": {"kind": "dream", "ref": "x", "date": "2026-10-12"}},
        {"failure_class": "bad_luck"},
        {"expect": {"envelope": {"max_len_mm": 1}}},
        {"expect": {"features": ["walkabel_top"]}},
        {"attempts": [{"file": "attempts/01.json", "expect_outcome": "nope"}]},
        {"attempts": [{"file": "attempts/01.json", "expect_outcome": "accepted", "extra": 1}]},
        {"failure_class": "intent_mismatch"},  # needs a golden design
        {"golden": {"params": {}}},  # neither design nor template
        {"golden": {"design": "g.json", "template": "shelf"}},
        {"id": "other_name"},
    ],
    ids=lambda c: next(iter(c)) + ":" + str(next(iter(c.values())))[:30],
)
def test_a_malformed_case_fails_to_load(tmp_path: Path, changes: dict[str, Any]) -> None:
    directory = _write_case(tmp_path, **changes)
    with pytest.raises(CaseError):
        load_case(directory)


def test_a_missing_attempt_file_fails_to_load(tmp_path: Path) -> None:
    directory = _write_case(tmp_path)
    (directory / "attempts" / "01.json").unlink()
    with pytest.raises(CaseError, match="Datei fehlt"):
        load_case(directory)


def test_a_missing_golden_file_fails_to_load(tmp_path: Path) -> None:
    directory = _write_case(tmp_path, golden={"design": "golden.json"})
    with pytest.raises(CaseError, match="Datei fehlt"):
        load_case(directory)


def test_an_attempt_record_with_an_unknown_key_fails_to_load(tmp_path: Path) -> None:
    directory = _write_case(tmp_path)
    path = directory / "attempts" / "01.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), "latency_ms": 12}))
    with pytest.raises(CaseError):
        load_case(directory)


def test_an_attempt_record_must_agree_with_its_outcome() -> None:
    with pytest.raises(ValidationError, match="accepted"):
        AttemptRecord(
            tool="save_design", outcome="engine_rejected", accepted=True, errors=[], raw_args={}
        )


def test_a_missing_case_file_fails_to_load(tmp_path: Path) -> None:
    (tmp_path / "empty_case").mkdir()
    with pytest.raises(CaseError, match=r"case\.json"):
        load_case(tmp_path / "empty_case")
