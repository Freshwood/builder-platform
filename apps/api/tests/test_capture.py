"""``capture``: a failed agent run becomes a draft regression case; ``promote`` makes it a case.

Everything runs offline in ``tmp_path`` (the draft root is overridable); no test writes into
``apps/api/tests/regressions``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from homeworking.bootstrap import build_container
from homeworking.modules.agent import capture
from homeworking.modules.agent.capture import CaptureError, RunData
from homeworking.modules.conversations.service import AgentRun
from homeworking.settings import Settings

BRIEF = (
    "Erstelle mir ein Podest für Kinder für eine Modenschau. Maximal 2 Meter lang und 1 Meter "
    "breit, drinnen. Rückfragen an kind.eltern@example.com bitte."
)
OWNER = "6f1c2a3e-1111-4222-8333-444455556666"
CHAT = "chat-secret-123"
RUN_ID = "0b6a2c1e-aaaa-4bbb-8ccc-0123456789ab"


def _attempt(outcome: str, errors: list[str], **extra: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "tool": "save_design",
        "tool_call_id": f"call_{len(errors)}{outcome[:3]}",
        "outcome": outcome,
        "accepted": outcome == "accepted",
        "errors": errors,
        "raw_args": {"title": "Podest", "design": {"object_type": "Podest"}},
        "design": None,
    }
    entry.update(extra)
    return entry


def _row(attempts: list[dict[str, Any]], run_id: str = RUN_ID, **changes: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": run_id,
        "owner_id": OWNER,
        "chat_id": CHAT,
        "status": "failed",
        "model": "upstage/solar-pro-4",
        "prompt_version": "2026-10-10-1",
        "error": "UsageLimitExceeded: request limit reached postgresql://app:hunter2@db/x",
        "created_at": "2026-10-11T09:30:00+00:00",
        "ui_messages": [
            {"id": "m1", "role": "user", "parts": [{"type": "text", "text": BRIEF}]},
            {"id": "m2", "role": "assistant", "parts": [{"type": "text", "text": "Abgebrochen"}]},
        ],
        "design_attempts": attempts,
    }
    row.update(changes)
    return row


def _engine_loop_row(**changes: Any) -> dict[str, Any]:
    attempts = [
        _attempt(
            "invalid_args", ["design.explanation: Extra inputs are not permitted [extra_forbidden]"]
        ),
        _attempt(
            "engine_rejected", ["Unbekannter Name 'surface_type' in der Formel von top_boards"]
        ),
        _attempt("engine_rejected", ["Teil 'deck' ragt über die Hülle hinaus"]),
    ]
    return _row(attempts, **changes)


def _args_syntax_row() -> dict[str, Any]:
    broken = '{"title": "Regal", "design": {"parts": [{"at": [0, 0, 18 +]}'
    return _row(
        [
            _attempt(
                "invalid_args",
                [
                    "Kein gültiges JSON (Expecting value bei Zeichen 51: …18 +]}…). Formeln in Anführungszeichen."
                ],
                raw_args=broken,
            )
        ]
    )


def _capture(row: dict[str, Any], root: Path, slug: str | None = None) -> Path:
    return capture.write_draft(capture.run_from_json(row), slug, root)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _all_text(directory: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in directory.rglob("*") if p.is_file())


# --------------------------------------------------------------------------------------------
# capture
# --------------------------------------------------------------------------------------------


def test_an_engine_loop_becomes_a_draft(tmp_path: Path) -> None:
    draft = _capture(_engine_loop_row(), tmp_path)

    assert draft.parent == tmp_path / "_drafts"
    assert sorted(p.name for p in draft.iterdir()) == ["attempts", "case.json", "golden.json"]
    assert sorted(p.name for p in (draft / "attempts").iterdir()) == [
        "01.json",
        "02.json",
        "03.json",
    ]
    case = _read(draft / "case.json")
    assert case["id"] == draft.name
    assert case["origin"] == {"kind": "agent_run", "ref": RUN_ID, "date": "2026-10-11"}
    assert case["failure_class"] == "schema_validation"  # first matching rule; the human confirms
    assert case["brief"].startswith("Erstelle mir ein Podest für Kinder")
    assert [a["expect_outcome"] for a in case["attempts"]] == [
        "invalid_args",
        "engine_rejected",
        "engine_rejected",
    ]
    assert case["attempts"][0]["errors_contain"] == ["design.explanation", "extra_forbidden"]
    assert case["attempts"][1]["errors_contain"] == [
        "Unbekannter Name 'surface_type' in der Formel von top_boards"
    ]
    assert "TODO" in case["title"]
    assert "TODO" in case["expect"]["note"]
    assert _read(draft / "golden.json").get("_todo")
    assert "invalid_args=1, engine_rejected=2" in case["notes"]
    # The recorded entry is stored unchanged.
    assert _read(draft / "attempts" / "02.json") == _engine_loop_row()["design_attempts"][1]


def test_two_engine_rejections_without_invalid_args_are_an_engine_loop(tmp_path: Path) -> None:
    attempts = [_attempt("engine_rejected", ["a"]), _attempt("engine_rejected", ["b"])]
    case = _read(_capture(_row(attempts), tmp_path) / "case.json")
    assert case["failure_class"] == "engine_loop"
    assert capture.guess_failure_class([_attempt("engine_rejected", ["a"])]) == "intent_mismatch"
    assert capture.guess_failure_class([]) == "intent_mismatch"


def test_unrepairable_json_is_an_args_syntax_failure(tmp_path: Path) -> None:
    draft = _capture(_args_syntax_row(), tmp_path)
    case = _read(draft / "case.json")
    assert case["failure_class"] == "args_syntax"
    assert isinstance(_read(draft / "attempts" / "01.json")["raw_args"], str)
    assert case["attempts"][0]["expect_outcome"] == "invalid_args"
    assert case["attempts"][0]["errors_contain"][0].startswith("Kein gültiges JSON")


def test_nothing_of_the_account_is_written(tmp_path: Path) -> None:
    draft = _capture(_engine_loop_row(), tmp_path)
    text = _all_text(draft)
    assert OWNER not in text
    assert CHAT not in text
    assert "kind.eltern@example.com" not in text
    assert "hunter2" not in text
    assert "[E-Mail entfernt]" in _read(draft / "case.json")["brief"]
    assert "://***@" in _read(draft / "case.json")["notes"]


def test_older_runs_without_outcome_and_raw_args_are_handled(tmp_path: Path) -> None:
    legacy = [
        {
            "tool": "save_design",
            "accepted": False,
            "errors": ["Teil ragt hinaus"],
            "design": {"x": 1},
        },
        {"tool": "save_design", "accepted": True, "errors": [], "design": {"x": 2}},
    ]
    draft = _capture(_row(legacy), tmp_path)
    case = _read(draft / "case.json")
    first = _read(draft / "attempts" / "01.json")
    assert first["outcome"] == "engine_rejected"
    assert first["raw_args"] is None
    assert _read(draft / "attempts" / "02.json")["outcome"] == "accepted"
    assert case["attempts"] == []  # not replayable without raw_args
    assert "outcome fehlt" in case["notes"]
    assert "nicht abspielbar" in case["notes"]
    # The draft files are what the loader accepts (apart from the placeholders).
    loader = capture.load_loader()
    loader.AttemptRecord.model_validate(first)


def test_a_truncated_call_is_kept_but_not_listed(tmp_path: Path) -> None:
    cut = _attempt(
        "invalid_args", ["x: y [z]"], raw_args='{"a": 1…[truncated, 300000 chars in total]'
    )
    case = _read(_capture(_row([cut]), tmp_path) / "case.json")
    assert case["attempts"] == []
    assert "nicht abspielbar" in case["notes"]


def test_the_brief_is_the_first_user_message_of_the_conversation(tmp_path: Path) -> None:
    earlier = [{"role": "user", "parts": [{"type": "text", "text": "Ein Regal für Bücher"}]}]
    row = _engine_loop_row(conversation_ui_messages=earlier)
    case = _read(_capture(row, tmp_path) / "case.json")
    assert case["brief"] == "Ein Regal für Bücher"
    assert "fehlgeschlagene Runde" in case["notes"]


def test_slug_is_ascii_snake_case_and_short() -> None:
    slug = capture.derive_slug(BRIEF, RUN_ID)
    assert slug == "podest_kinder_modenschau_maximal_2_meter"
    assert (
        capture.derive_slug("Größe ändern: Tür für Überdachung!", RUN_ID)
        == "groesse_aendern_tuer_ueberdachung"
    )
    long = capture.derive_slug("wort " * 30, RUN_ID)
    assert len(long) <= capture.SLUG_MAX
    assert capture.SLUG_PATTERN.match(long)
    assert capture.derive_slug("!!!", "ABCD-1234-xyz").startswith("run_abcd1234")
    assert capture.derive_slug("2 Regale", RUN_ID).startswith("run_")


def test_capture_never_overwrites(tmp_path: Path) -> None:
    draft = _capture(_engine_loop_row(), tmp_path, slug="podest")
    before = _all_text(draft)

    with pytest.raises(CaptureError, match="schon erfasst"):  # same run again
        _capture(_engine_loop_row(), tmp_path, slug="other")
    other = _engine_loop_row(id=str(uuid4()))
    with pytest.raises(CaptureError, match="existiert bereits"):  # same explicit slug
        _capture(other, tmp_path, slug="podest")
    with pytest.raises(CaptureError, match="ungültig"):
        _capture(other, tmp_path, slug="Podest!")
    (tmp_path / "taken_case").mkdir()
    with pytest.raises(CaptureError, match="existiert bereits"):  # a promoted case blocks it too
        _capture(other, tmp_path, slug="taken_case")

    # An automatic slug that collides gets a suffix instead.
    first = _capture(_engine_loop_row(id=str(uuid4())), tmp_path)
    second = _capture(_engine_loop_row(id=str(uuid4())), tmp_path)
    assert second.name.endswith("_2")
    assert second.name != first.name
    assert len(second.name) <= capture.SLUG_MAX
    assert _all_text(draft) == before


def test_the_cli_reads_an_exported_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    export = tmp_path / "row.json"
    export.write_text(json.dumps(_args_syntax_row()), encoding="utf-8")
    root = tmp_path / "regressions"
    root.mkdir()
    monkeypatch.setattr(capture, "REGRESSIONS_DIR", root)

    capture.main(["--from-json", str(export)])
    out = capsys.readouterr().out
    assert "Entwurf geschrieben" in out
    assert (root / "_drafts").is_dir()
    with pytest.raises(SystemExit, match="schon erfasst"):
        capture.main(["--from-json", str(export)])
    with pytest.raises(SystemExit, match="Entwurf 'nope' nicht gefunden"):
        capture.main(["promote", "nope", "--no-run"])


# --------------------------------------------------------------------------------------------
# promote
# --------------------------------------------------------------------------------------------


def _complete(draft: Path) -> None:
    """What the maintainer does: title, expect, golden, class, outcomes; TODO lines removed."""
    path = draft / "case.json"
    case = _read(path)
    case["failure_class"] = "intent_mismatch"
    case["title"] = "Podest für Kinder"
    case["expect"] = {"envelope": {"max_length_mm": 2000}, "use": "indoor"}
    case["golden"] = {"template": "shelf", "params": {}}
    case["notes"] = "Bearbeitet."
    path.write_text(json.dumps(case), encoding="utf-8")
    (draft / "golden.json").unlink()


def test_a_draft_with_placeholders_is_refused(tmp_path: Path) -> None:
    draft = _capture(_engine_loop_row(), tmp_path)
    with pytest.raises(CaptureError, match="TODO") as refused:
        capture.promote(draft.name, tmp_path, run_checks=False)
    assert "golden.json ist noch der Platzhalter" in str(refused.value)
    assert draft.is_dir()
    assert not (tmp_path / draft.name).exists()


def test_a_draft_without_expectations_is_refused(tmp_path: Path) -> None:
    draft = _capture(_engine_loop_row(), tmp_path)
    _complete(draft)
    case = _read(draft / "case.json")
    case["expect"] = {"note": "Nutzer wollte ein Podest"}
    (draft / "case.json").write_text(json.dumps(case), encoding="utf-8")
    with pytest.raises(CaptureError, match="keine Bedingung"):
        capture.promote(draft.name, tmp_path, run_checks=False)


def test_a_malformed_draft_is_refused_with_the_loader_message(tmp_path: Path) -> None:
    draft = _capture(_engine_loop_row(), tmp_path)
    _complete(draft)
    case = _read(draft / "case.json")
    case["colour"] = "red"
    (draft / "case.json").write_text(json.dumps(case), encoding="utf-8")
    with pytest.raises(CaptureError, match="nicht ladbar"):
        capture.promote(draft.name, tmp_path, run_checks=False)
    assert draft.is_dir()


def test_a_completed_draft_is_promoted_and_discovered(tmp_path: Path) -> None:
    draft = _capture(_engine_loop_row(), tmp_path)
    loader = capture.load_loader()
    assert loader.case_directories(tmp_path) == []  # drafts are no cases
    _complete(draft)

    target = capture.promote(draft.name, tmp_path, run_checks=False)

    assert target == tmp_path / draft.name
    assert not draft.exists()
    assert loader.case_directories(tmp_path) == [target]
    loaded = loader.load_all(tmp_path)
    assert [c.slug for c in loaded] == [draft.name]
    assert loaded[0].case.origin.ref == RUN_ID
    # Promoting again, or over an existing case, never overwrites.
    with pytest.raises(CaptureError, match="nicht gefunden"):
        capture.promote(draft.name, tmp_path, run_checks=False)
    again = _capture(_engine_loop_row(id=str(uuid4())), tmp_path, slug="zweiter")
    _complete(again)
    (tmp_path / "zweiter").mkdir()
    with pytest.raises(CaptureError, match="existiert bereits"):
        capture.promote("zweiter", tmp_path, run_checks=False)


def test_promote_stops_when_the_replay_is_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    draft = _capture(_engine_loop_row(), tmp_path)
    _complete(draft)
    seen: dict[str, Path] = {}

    def red(slug: str, drafts_dir: Path) -> tuple[bool, str]:
        seen["dir"] = drafts_dir
        return False, "1 failed"

    monkeypatch.setattr(capture, "run_replay", red)
    with pytest.raises(CaptureError, match="rot, nichts verschoben"):
        capture.promote(draft.name, tmp_path)
    assert draft.is_dir()
    assert seen["dir"] == tmp_path / "_drafts"

    monkeypatch.setattr(capture, "run_replay", lambda slug, drafts_dir: (True, ""))
    assert capture.promote(draft.name, tmp_path) == tmp_path / draft.name


def test_the_replay_command_selects_the_case() -> None:
    command = capture.pytest_command("podest")
    assert command[1:4] == ["-m", "pytest", "apps/api/tests/test_regressions.py"]
    assert command[command.index("-k") + 1] == "podest"


# --------------------------------------------------------------------------------------------
# Reading a row from the database
# --------------------------------------------------------------------------------------------


async def test_a_run_is_read_from_the_database(settings: Settings) -> None:
    container = build_container(settings)
    await container.create_schema()
    try:
        owner = (await container.identity.create_guest()).id

        async def record(text: str, attempts: list[dict[str, Any]]) -> str:
            trace = uuid4().hex
            await container.conversations.record(
                AgentRun(
                    trace_id=trace,
                    owner_id=owner,
                    chat_id="chat-1",
                    project_id=None,
                    status="failed",
                    model="test",
                    prompt_version="v",
                    ui_messages=[{"role": "user", "parts": [{"type": "text", "text": text}]}],
                    design_attempts=attempts,
                    error="boom",
                )
            )
            return trace

        await record("Erste Frage", [])
        trace_id = await record("Zweite Frage", [_attempt("engine_rejected", ["x"])])
    finally:
        await container.close()

    run = await capture.fetch_run(trace_id, settings.database_url)  # by trace id
    run_id = run.run_id
    run = await capture.fetch_run(run_id, settings.database_url)  # by agent_runs.id

    assert isinstance(run, RunData)
    assert run.run_id == run_id
    assert capture.user_text(run.conversation_ui_messages) == "Erste Frage"
    assert run.design_attempts[0]["outcome"] == "engine_rejected"
    assert not hasattr(run, "owner_id")
    with pytest.raises(CaptureError, match="nicht in agent_runs"):
        await capture.fetch_run(str(uuid4()), settings.database_url)


async def test_a_database_failure_does_not_leak_the_connection_string(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'missing' / 'x.db'}"
    with pytest.raises(CaptureError) as failed:
        await capture.fetch_run(str(uuid4()), url)
    assert str(tmp_path) not in str(failed.value)
    assert "DATABASE_URL" in str(failed.value)
