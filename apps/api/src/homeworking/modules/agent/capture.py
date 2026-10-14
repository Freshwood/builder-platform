"""Turn a failed agent run into a regression case (``task regress:capture``).

    uv run python -m homeworking.modules.agent.capture <run_id> [--slug NAME] [--from-json FILE]
    uv run python -m homeworking.modules.agent.capture promote <slug> [--no-run]

``capture`` reads one ``agent_runs`` row (through the app's own database access, so SQLite and
PostgreSQL both work; ``--from-json`` takes an exported row instead and needs no database) and
writes a DRAFT to ``apps/api/tests/regressions/_drafts/<slug>/``. The draft already holds the
recorded tool calls (``attempts/NN.json``) and a guessed ``failure_class``; the title, the
``expect`` block and the golden design are ``TODO`` placeholders for a human (see the
``regress-capture`` skill). Nothing from the user account is copied: no user id, no chat id, no
e-mail address, no connection string.

``promote`` loads the draft with the real case loader, refuses while a ``TODO`` is left, replays
the case with the regression tests (``test_regressions.py``) and only then moves the directory
from ``_drafts/`` to ``regressions/<slug>/``.

Format of an exported row (``--from-json``): the columns ``id``, ``created_at``, ``status``,
``model``, ``prompt_version``, ``error``, ``ui_messages``, ``design_attempts``, and optionally
``conversation_ui_messages`` (UI messages of the earlier turns of the chat, oldest first) and
``usage`` (only its ``failed_request`` is read: the shape of the request the provider rejected,
see ``request_shape.py``; it becomes a line in ``notes`` and the file ``failed_request.json``).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID

REPO_ROOT = Path(__file__).resolve().parents[6]
REGRESSIONS_DIR = REPO_ROOT / "apps" / "api" / "tests" / "regressions"
LOADER_PATH = REGRESSIONS_DIR / "loader.py"
DRAFTS_DIRNAME = "_drafts"

SLUG_MAX = 40
SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
TODO = "TODO"
#: Keys of a ``design_attempts`` entry that the case loader accepts (``AttemptRecord``).
ATTEMPT_KEYS = ("tool", "tool_call_id", "outcome", "accepted", "errors", "raw_args", "design")
_TRUNCATED = "[truncated,"
# Matched after transliteration to ASCII ("für" -> "fuer").
_FILLER_WORDS = frozenset(
    {
        *("ich", "mir", "mich", "mein", "meine", "meinen", "ein", "eine", "einen", "einem"),
        *("einer", "der", "die", "das", "den", "dem", "und", "oder", "bitte", "erstelle"),
        *("erstell", "mach", "baue", "bauen", "moechte", "will", "soll", "sollen", "wir"),
        *("fuer", "gern", "gerne", "mal", "kann", "koennte"),
    }
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL_CREDENTIALS = re.compile(r"://[^/\s:@]+:[^/\s@]*@")


class CaptureError(Exception):
    """Capture or promote refused; the message is for the user (German)."""


# --------------------------------------------------------------------------------------------
# The case loader lives next to the tests; load it by path (it is no importable package)
# --------------------------------------------------------------------------------------------


def load_loader() -> ModuleType:
    """Import ``apps/api/tests/regressions/loader.py`` (the authoritative case schema)."""
    name = "regression_case_loader"
    if name in sys.modules:
        return sys.modules[name]
    path = LOADER_PATH
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise CaptureError(f"{path}: kann nicht geladen werden")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # pydantic resolves postponed annotations through sys.modules
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------------------------
# Reading a run
# --------------------------------------------------------------------------------------------


@dataclass
class RunData:
    """The parts of an ``agent_runs`` row a draft needs. No owner, chat or user ids."""

    run_id: str
    created: date | None
    status: str
    model: str
    prompt_version: str
    error: str | None
    ui_messages: list[Any]
    design_attempts: list[Any]
    conversation_ui_messages: list[Any] = field(default_factory=list)
    # ``usage["failed_request"]`` of the row: structure of the rejected request, never text.
    failed_request: dict[str, Any] | None = None


def failed_request_of(usage: Any) -> dict[str, Any] | None:
    """The stored shape of a failed model request out of ``agent_runs.usage``, if any."""
    record = usage.get("failed_request") if isinstance(usage, dict) else None
    return record if isinstance(record, dict) else None


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None
    return None


def run_from_json(data: Any, run_id: str | None = None) -> RunData:
    """Build :class:`RunData` from an exported ``agent_runs`` row."""
    if not isinstance(data, dict):
        raise CaptureError("Der Export muss ein JSON-Objekt (eine agent_runs-Zeile) sein.")
    attempts = data.get("design_attempts")
    if not isinstance(attempts, list):
        raise CaptureError("Der Export hat kein 'design_attempts' (Liste).")
    ident = run_id or data.get("id")
    if not ident:
        raise CaptureError("Der Export hat keine 'id'; Lauf-ID als Argument angeben.")
    return RunData(
        run_id=str(ident),
        created=_as_date(data.get("created_at")),
        status=str(data.get("status") or "unbekannt"),
        model=str(data.get("model") or "unbekannt"),
        prompt_version=str(data.get("prompt_version") or "unbekannt"),
        error=data.get("error") if isinstance(data.get("error"), str) else None,
        ui_messages=list(data.get("ui_messages") or []),
        design_attempts=attempts,
        conversation_ui_messages=list(data.get("conversation_ui_messages") or []),
        failed_request=failed_request_of(data.get("usage")),
    )


async def fetch_run(run_id: str, database_url: str | None = None) -> RunData:
    """Read the run (by ``agent_runs.id``, else ``trace_id``) and the chat's first turn.

    Uses the same engine and session factory as the application, so the SQLite development
    database and PostgreSQL work alike. ``database_url`` overrides ``Settings.database_url``.
    """
    from sqlalchemy import select

    from homeworking.db.schema import AgentRunRow
    from homeworking.db.session import make_engine, make_session_factory
    from homeworking.settings import Settings

    url = database_url or Settings().database_url
    engine = make_engine(url)
    sessions = make_session_factory(engine)
    try:
        async with sessions() as session:
            row = None
            with contextlib.suppress(ValueError):  # not a UUID: try the trace id
                row = await session.get(AgentRunRow, UUID(run_id))
            if row is None:
                row = await session.scalar(
                    select(AgentRunRow).where(AgentRunRow.trace_id == run_id)
                )
            if row is None:
                raise CaptureError(f"Lauf '{run_id}' nicht in agent_runs gefunden.")
            scope = None
            if row.chat_id is not None:
                scope = AgentRunRow.chat_id == row.chat_id
            elif row.project_id is not None:
                scope = AgentRunRow.project_id == row.project_id
            first_turn: list[Any] = []
            if scope is not None:
                first = await session.scalar(
                    select(AgentRunRow)
                    .where(AgentRunRow.owner_id == row.owner_id, scope)
                    .order_by(AgentRunRow.created_at, AgentRunRow.id)
                    .limit(1)
                )
                if first is not None and first.id != row.id:
                    first_turn = list(first.ui_messages or [])
            return RunData(
                run_id=str(row.id),
                created=_as_date(row.created_at),
                status=row.status,
                model=row.model,
                prompt_version=row.prompt_version,
                error=row.error,
                ui_messages=list(row.ui_messages or []),
                design_attempts=list(row.design_attempts or []),
                conversation_ui_messages=first_turn,
                failed_request=failed_request_of(row.usage),
            )
    except CaptureError:
        raise
    except Exception as error:
        # Never echo the exception text: driver messages can contain host and user names.
        raise CaptureError(
            f"Datenbankzugriff fehlgeschlagen ({type(error).__name__}). DATABASE_URL prüfen "
            "oder den Lauf mit --from-json aus einem Export lesen."
        ) from None
    finally:
        await engine.dispose()


# --------------------------------------------------------------------------------------------
# Building the draft
# --------------------------------------------------------------------------------------------


def user_text(messages: list[Any]) -> str | None:
    """Text of the first user message (UI message format: ``parts`` with ``type == 'text'``)."""
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        parts = message.get("parts") or []
        text = "\n".join(
            p["text"] for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str)
        ).strip()
        if text:
            return text
    return None


def redact_email(text: str) -> tuple[str, bool]:
    redacted = _EMAIL.sub("[E-Mail entfernt]", text)
    return redacted, redacted != text


def derive_slug(brief: str, run_id: str) -> str:
    """ASCII snake_case slug of at most ``SLUG_MAX`` characters from the brief."""
    text = brief
    for source, target in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.lower().replace(source, target)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    words = re.findall(r"[a-z0-9]+", text)
    kept = [w for w in words if w not in _FILLER_WORDS] or words
    slug = ""
    for word in kept:
        candidate = f"{slug}_{word}" if slug else word
        if len(candidate) > SLUG_MAX:
            break
        slug = candidate
    if not slug:
        slug = f"run_{re.sub('[^a-z0-9]', '', run_id.lower())[:8]}"
    if not slug[0].isalpha():
        slug = f"run_{slug}"[:SLUG_MAX]
    return slug.rstrip("_")


def _is_truncated(raw_args: Any) -> bool:
    return isinstance(raw_args, str) and _TRUNCATED in raw_args[-120:]


def normalise_attempt(entry: Any) -> tuple[dict[str, Any], list[str]]:
    """Keep the entry as stored; fill what older runs lack. Returns ``(entry, remarks)``."""
    if not isinstance(entry, dict):
        raise CaptureError("design_attempts enthält einen Eintrag, der kein Objekt ist.")
    remarks: list[str] = []
    out = {key: entry[key] for key in ATTEMPT_KEYS if key in entry}
    dropped = sorted(set(entry) - set(ATTEMPT_KEYS))
    if dropped:
        remarks.append(f"unbekannte Schlüssel entfernt: {', '.join(dropped)}")
    out.setdefault("tool", "unbekannt")
    out.setdefault("errors", [])
    if "outcome" not in out:
        out["outcome"] = "accepted" if out.get("accepted") else "engine_rejected"
        remarks.append("outcome fehlt (älterer Lauf), aus accepted abgeleitet")
    out["accepted"] = out["outcome"] == "accepted"
    if "raw_args" not in out:
        out["raw_args"] = None
        remarks.append("raw_args fehlt (älterer Lauf), nicht abspielbar")
    return out, remarks


def _error_fragments(errors: list[str]) -> list[str]:
    """First distinctive fragment of the errors: ``loc`` and type of a pydantic line, else a cut."""
    for line in errors:
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^([\w.\[\]]+): .* \[([a-z_]+)\]$", line)
        if match:
            return [match.group(1), match.group(2)]
        if len(line) <= 60:
            return [line]
        return [line[:60].rsplit(" ", 1)[0].rstrip(",.;:")]
    return []


def guess_failure_class(attempts: list[dict[str, Any]]) -> str:
    """Heuristic only; the maintainer confirms it (see the skill's failure-class table)."""
    invalid = [a for a in attempts if a["outcome"] == "invalid_args"]
    if any("Kein gültiges JSON" in e or "Invalid JSON" in e for a in invalid for e in a["errors"]):
        return "args_syntax"
    if invalid:
        return "schema_validation"
    if sum(a["outcome"] == "engine_rejected" for a in attempts) >= 2:
        return "engine_loop"
    return "intent_mismatch"


def _small_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number(value: Any) -> str:
    return "?" if (number := _small_int(value)) is None else str(number)


def describe_failed_request(record: dict[str, Any]) -> str:
    """One German line about the rejected request (class, status, number, suspicious indices).

    Reads only numbers and a class name from the record; it never copies free text.
    """
    error = record.get("error_class")
    error_class = error if isinstance(error, str) and re.fullmatch(r"\w{1,80}", error) else None
    provider = record.get("provider")
    provider = provider if isinstance(provider, dict) else {}
    suspicious = [i for i in provider.get("suspicious") or [] if _small_int(i) is not None]
    where = (
        f"auffällige Provider-Nachrichten messages{suspicious}"
        if suspicious
        else "keine auffällige Provider-Nachricht erkannt"
        if provider.get("available")
        else "Provider-Array nicht ermittelbar"
    )
    return (
        f"Abgelehnte Anfrage Nr. {_number(record.get('request_number'))}: "
        f"{error_class or 'Fehlerklasse unbekannt'}, HTTP {_number(record.get('status_code'))}, "
        f"{_number(record.get('messages_total'))} Nachrichten, {where}; "
        "Aufbau in failed_request.json."
    )


def _scrub(text: str) -> str:
    text = _URL_CREDENTIALS.sub("://***@", text)
    return redact_email(text)[0]


def _existing_refs(root: Path) -> dict[str, Path]:
    """Run ids already captured (cases and drafts) -> their directory."""
    found: dict[str, Path] = {}
    for base in (root, root / DRAFTS_DIRNAME):
        if not base.is_dir():
            continue
        for case_file in base.glob("*/case.json"):
            try:
                ref = json.loads(case_file.read_text(encoding="utf-8"))["origin"]["ref"]
            except (OSError, ValueError, KeyError, TypeError):
                continue
            found[str(ref)] = case_file.parent
    return found


def _taken(root: Path, slug: str) -> bool:
    return (root / slug).exists() or (root / DRAFTS_DIRNAME / slug).exists()


def pick_slug(root: Path, wanted: str | None, brief: str, run_id: str) -> str:
    if wanted is not None:
        if not SLUG_PATTERN.match(wanted) or len(wanted) > SLUG_MAX:
            raise CaptureError(
                f"Slug '{wanted}' ungültig: [a-z][a-z0-9_]*, höchstens {SLUG_MAX} Zeichen."
            )
        if _taken(root, wanted):
            raise CaptureError(
                f"Fall oder Entwurf '{wanted}' existiert bereits (nichts überschrieben)."
            )
        return wanted
    base = derive_slug(brief, run_id)
    slug, n = base, 1
    while _taken(root, slug):
        n += 1
        suffix = f"_{n}"
        slug = f"{base[: SLUG_MAX - len(suffix)]}{suffix}"
    return slug


def build_draft(
    run: RunData, slug: str, today: date | None = None
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Return ``(case.json, golden.json, attempt files)`` for the draft."""
    remarks: list[str] = []
    attempts: list[dict[str, Any]] = []
    for index, entry in enumerate(run.design_attempts, start=1):
        record, entry_remarks = normalise_attempt(entry)
        attempts.append(record)
        remarks += [f"{index:02d}: {r}" for r in entry_remarks]

    first = user_text(run.conversation_ui_messages) or user_text(run.ui_messages)
    own = user_text(run.ui_messages)
    if first is None:
        brief = f"{TODO}: Nutzertext fehlt im Lauf, aus dem Bericht einsetzen"
        remarks.append("kein Nutzertext im Lauf gefunden")
    else:
        brief, redacted = redact_email(first)
        if redacted:
            remarks.append("E-Mail-Adresse im Nutzertext entfernt")
    if own and first and own != first:
        remarks.append(
            "fehlgeschlagene Runde (letzte Nutzernachricht): " + redact_email(own)[0][:500]
        )

    refs: list[dict[str, Any]] = []
    skipped: list[str] = []
    for index, record in enumerate(attempts, start=1):
        if record["raw_args"] is None or _is_truncated(record["raw_args"]):
            skipped.append(f"{index:02d}")
            continue
        ref: dict[str, Any] = {
            "file": f"attempts/{index:02d}.json",
            "expect_outcome": record["outcome"],
        }
        if fragments := _error_fragments(record["errors"]):
            ref["errors_contain"] = fragments
        refs.append(ref)
    if skipped:
        remarks.append(
            f"Versuche {', '.join(skipped)} sind nicht abspielbar (raw_args fehlt oder gekürzt) "
            "und stehen nicht in 'attempts'; die Dateien bleiben als Beleg liegen"
        )

    failure_class = guess_failure_class(attempts)
    outcomes = ", ".join(f"{k}={v}" for k, v in Counter(a["outcome"] for a in attempts).items())
    header = [
        f"{TODO}: failure_class bestätigen (Heuristik: {failure_class}), title, expect und golden "
        f"ausfüllen, expect_outcome der Versuche prüfen, dann diese Zeile löschen.",
        f"Lauf {run.status}, Modell {run.model}, Prompt {run.prompt_version}; "
        f"Ergebnisse: {outcomes or 'keine Versuche'}.",
    ]
    if run.error:
        header.append(f"Fehler des Laufs: {_scrub(run.error)[:300]}")
    if run.failed_request is not None:
        header.append(describe_failed_request(run.failed_request))
    notes = "\n".join([*header, *remarks])

    case = {
        "id": slug,
        "title": f"{TODO}: Kurztitel (Entwurf aus Lauf {run.run_id[:8]})",
        "origin": {
            "kind": "agent_run",
            "ref": run.run_id,
            "date": (run.created or today or date.today()).isoformat(),
        },
        "failure_class": failure_class,
        "brief": brief,
        "expect": {
            "note": f"{TODO}: nur Vorgaben aus dem Nutzertext als Bedingungen eintragen "
            "(envelope, use, support, materials_any/none, features); nichts erfinden"
        },
        "attempts": refs,
        "golden": {"design": "golden.json", "params": {}},
        "notes": notes,
    }
    golden = {
        "_todo": f"{TODO}: durch das korrigierte AssemblyDesign ersetzen (über die Engine "
        "gebaut), das den Nutzertext erfüllt; bei args_syntax/schema_validation darf der "
        "'golden'-Block in case.json entfallen."
    }
    return case, golden, attempts


def _dump(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_draft(run: RunData, slug: str | None = None, root: Path = REGRESSIONS_DIR) -> Path:
    """Write the draft directory; never overwrites an existing case or draft."""
    existing = _existing_refs(root).get(run.run_id)
    if existing is not None:
        raise CaptureError(
            f"Lauf {run.run_id} ist schon erfasst: {existing.name} (nichts überschrieben)."
        )
    brief = user_text(run.conversation_ui_messages) or user_text(run.ui_messages) or ""
    chosen = pick_slug(root, slug, brief, run.run_id)
    case, golden, attempts = build_draft(run, chosen)
    directory = root / DRAFTS_DIRNAME / chosen
    (directory / "attempts").mkdir(parents=True, exist_ok=False)
    for index, record in enumerate(attempts, start=1):
        _dump(directory / "attempts" / f"{index:02d}.json", record)
    _dump(directory / "golden.json", golden)
    if run.failed_request is not None:
        # Beside the case, not part of it: the case loader reads only the files it names.
        _dump(directory / "failed_request.json", run.failed_request)
    _dump(directory / "case.json", case)
    return directory


# --------------------------------------------------------------------------------------------
# promote
# --------------------------------------------------------------------------------------------


def todo_problems(case: Any, golden: dict[str, Any] | None) -> list[str]:
    """Placeholders and gaps that keep a draft from becoming a case."""
    problems: list[str] = []
    for label, value in (
        ("title", case.title),
        ("brief", case.brief),
        ("notes", case.notes),
        ("expect.note", case.expect.note or ""),
    ):
        if TODO in value:
            problems.append(f"{label} enthält noch ein {TODO}")
    constraints = case.expect.model_dump(exclude_defaults=True)
    constraints.pop("note", None)
    needs_golden = case.failure_class not in {"args_syntax", "schema_validation"}
    if not constraints and needs_golden:
        problems.append("expect enthält keine Bedingung (nur Vorgaben aus dem Nutzertext)")
    if golden is not None and "_todo" in golden:
        problems.append("golden.json ist noch der Platzhalter")
    if case.golden is not None and case.golden.design is not None and not golden:
        problems.append("golden.json fehlt oder ist leer")
    return problems


def pytest_command(slug: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        "apps/api/tests/test_regressions.py",
        "-k",
        slug,
        "-q",
        "-p",
        "no:cacheprovider",
    ]


def run_replay(slug: str, drafts_dir: Path) -> tuple[bool, str]:
    """Run the replay and golden tests for one draft (``REGRESSION_CASES_DIR`` = drafts dir)."""
    env = {**os.environ, "REGRESSION_CASES_DIR": str(drafts_dir)}
    result = subprocess.run(  # noqa: S603
        pytest_command(slug),
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0, (result.stdout + result.stderr)[-3000:]


def promote(slug: str, root: Path = REGRESSIONS_DIR, *, run_checks: bool = True) -> Path:
    """Move ``_drafts/<slug>`` to ``<slug>`` once it loads cleanly and its tests pass."""
    drafts = root / DRAFTS_DIRNAME
    draft = drafts / slug
    target = root / slug
    if not draft.is_dir():
        raise CaptureError(f"Entwurf '{slug}' nicht gefunden ({DRAFTS_DIRNAME}/{slug}).")
    if target.exists():
        raise CaptureError(f"Fall '{slug}' existiert bereits (nichts überschrieben).")
    loader = load_loader()
    try:
        loaded = loader.load_case(draft)
    except loader.CaseError as error:
        raise CaptureError(f"Entwurf nicht ladbar: {error}") from None
    if problems := todo_problems(loaded.case, loaded.golden_design):
        raise CaptureError("Entwurf noch nicht fertig:\n  - " + "\n  - ".join(problems))
    if loaded.case.golden is not None:
        _check_golden_source(loaded)
    if run_checks:
        ok, output = run_replay(slug, drafts)
        if not ok:
            raise CaptureError(
                "Replay/Golden-Prüfung rot, nichts verschoben. Befehl: "
                f"REGRESSION_CASES_DIR={drafts} {' '.join(pytest_command(slug))}\n{output}"
            )
    draft.rename(target)
    return target


def _check_golden_source(loaded: Any) -> None:
    """The golden design must parse as an ``AssemblyDesign``."""
    from pydantic import ValidationError

    from construction_model.assembly import AssemblyDesign

    if loaded.golden_design is not None:
        try:
            AssemblyDesign.model_validate(loaded.golden_design)
        except ValidationError as error:
            raise CaptureError(f"golden.json ist kein gültiges AssemblyDesign: {error}") from None


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


def _capture_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="capture",
        description=(
            "Entwurf eines Regressionsfalls aus einem fehlgeschlagenen Agentenlauf. "
            "Mit 'capture promote <slug>' wird ein fertiger Entwurf zum Fall."
        ),
    )
    parser.add_argument("run_id", nargs="?", help="agent_runs.id (oder trace_id)")
    parser.add_argument("--slug", help="Name des Falls (snake_case, ASCII, <= 40 Zeichen)")
    parser.add_argument("--from-json", type=Path, help="exportierte agent_runs-Zeile statt DB")
    return parser


def _promote_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="capture promote")
    parser.add_argument("slug")
    parser.add_argument(
        "--no-run", action="store_true", help="Tests nicht ausführen, nur die Ladeprüfung"
    )
    return parser


def _shown(path: Path) -> Path:
    return path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if args[:1] == ["promote"]:
            options = _promote_parser().parse_args(args[1:])
            target = promote(options.slug, REGRESSIONS_DIR, run_checks=not options.no_run)
            print(f"Fall übernommen: {_shown(target)}")
            print("Nächster Schritt: task regress (nicht committen, das macht der Maintainer).")
            return
        parser = _capture_parser()
        options = parser.parse_args(args)
        if options.from_json is not None:
            try:
                data = json.loads(options.from_json.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise CaptureError(
                    f"{options.from_json}: nicht lesbar ({type(error).__name__})"
                ) from None
            run = run_from_json(data, options.run_id)
        elif options.run_id:
            run = asyncio.run(fetch_run(options.run_id))
        else:
            parser.error("run_id oder --from-json angeben")
        directory = write_draft(run, options.slug, REGRESSIONS_DIR)
    except CaptureError as error:
        sys.exit(str(error))
    print(f"Entwurf geschrieben: {_shown(directory)}")
    print("Nächste Schritte (Skill regress-capture): title, expect, golden und failure_class")
    print(f"ausfüllen, dann: task regress:promote -- {directory.name}")


if __name__ == "__main__":
    main()
