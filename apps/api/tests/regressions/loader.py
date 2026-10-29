"""Regression cases: the format of ``<slug>/case.json`` and the code that loads it.

One directory per case. ``README.md`` in this directory describes the files; this module is the
authoritative schema (every model forbids unknown keys, so a typo fails at load time instead of
silently weakening a case).
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from homeworking.calc_engine.assembly.intent import Expectation
from homeworking.calc_engine.pipeline.budget import Complexity
from homeworking.construction_model.base import ParamValue

#: ``REGRESSION_CASES_DIR`` lets ``capture promote`` replay a draft in ``_drafts/`` with the very
#: same tests, before the draft becomes a case.
CASES_DIR = Path(os.environ.get("REGRESSION_CASES_DIR") or Path(__file__).resolve().parent)
#: Work in progress (``task regress:capture``); never discovered as a case.
DRAFTS_DIRNAME = "_drafts"

FailureClass = Literal[
    "args_syntax",
    "schema_validation",
    "engine_loop",
    "intent_mismatch",
    "drawing_defect",
    "slow_design",
]
Outcome = Literal[
    "accepted",
    "engine_rejected",
    "invalid_args",
    "parameter_error",
    "command_error",
    "not_found",
    "unknown_pack",
    "no_project",
    "exception",
]
#: Failure classes whose bug is the call itself: no design has to exist to describe a fix.
CLASSES_WITHOUT_REFERENCE: frozenset[str] = frozenset(
    {"args_syntax", "schema_validation", "slow_design"}
)


class CaseError(ValueError):
    """A case directory is malformed (missing file, unreadable JSON, inconsistent fields)."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Origin(_Model):
    kind: Literal["agent_run", "bug_report", "hand_written"]
    ref: str = Field(min_length=1, description="agent_runs id, or path/commit of the report")
    date: date


class AttemptRef(_Model):
    """One recorded tool call (``attempts/NN.json``) and what the replay must show."""

    file: str = Field(pattern=r"^attempts/[A-Za-z0-9_.-]+\.json$")
    expect_outcome: Outcome
    errors_contain: list[str] = Field(
        default_factory=list, description="Substrings that must occur in the replayed errors"
    )
    synthetic: bool = Field(
        False, description="Reconstructed from a report, not recorded from a real run"
    )


class AttemptRecord(_Model):
    """The shape of ``agent_runs.design_attempts`` entries (see ``tool_attempt``)."""

    tool: str
    tool_call_id: str | None = None
    outcome: Outcome
    accepted: bool
    errors: list[str]
    raw_args: str | dict[str, Any] | None
    design: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _accepted_matches_outcome(self) -> AttemptRecord:
        if self.accepted != (self.outcome == "accepted"):
            raise ValueError("accepted must be true exactly when outcome is 'accepted'")
        return self


class Reference(_Model):
    """The correct construction: a design file in the case directory and its parameters."""

    design: str = Field(pattern=r"^[A-Za-z0-9_.-]+\.json$")
    params: dict[str, ParamValue] = Field(default_factory=dict)


class RegressionCase(_Model):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$", description="Equals the directory name")
    title: str = Field(min_length=1)
    origin: Origin
    failure_class: FailureClass
    brief: str = Field(min_length=1, description="The user's text, verbatim")
    complexity: Complexity | None = Field(
        None, description="Time budget category; empty = the engine classifies the brief"
    )
    expect: Expectation
    attempts: list[AttemptRef] = Field(default_factory=list)
    reference: Reference | None = None
    notes: str = ""

    @model_validator(mode="after")
    def _reference_is_present_where_needed(self) -> RegressionCase:
        if self.reference is None and self.failure_class not in CLASSES_WITHOUT_REFERENCE:
            raise ValueError(f"failure_class '{self.failure_class}' needs a reference design")
        return self


class LoadedCase:
    """A validated case with its attempt records and reference design read from disk."""

    def __init__(
        self,
        directory: Path,
        case: RegressionCase,
        attempts: list[AttemptRecord],
        reference_design: dict[str, Any] | None,
    ) -> None:
        self.directory = directory
        self.case = case
        self.attempts = attempts
        self.reference_design = reference_design

    @property
    def slug(self) -> str:
        return self.directory.name


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CaseError(f"{path}: Datei fehlt") from None
    except json.JSONDecodeError as error:
        raise CaseError(f"{path}: kein gültiges JSON ({error})") from error


def load_case(directory: Path) -> LoadedCase:
    """Load and validate one case directory; raises ``CaseError`` on any inconsistency."""
    try:
        case = RegressionCase.model_validate(_read_json(directory / "case.json"))
        if case.id != directory.name:
            raise CaseError(f"{directory}: id '{case.id}' passt nicht zum Verzeichnisnamen")
        attempts = [
            AttemptRecord.model_validate(_read_json(directory / ref.file)) for ref in case.attempts
        ]
        reference_design: dict[str, Any] | None = None
        if case.reference is not None:
            data = _read_json(directory / case.reference.design)
            if not isinstance(data, dict):
                raise CaseError(f"{directory / case.reference.design}: erwartet ein JSON-Objekt")
            reference_design = data
    except ValidationError as error:
        raise CaseError(f"{directory}: {error}") from error
    return LoadedCase(directory, case, attempts, reference_design)


def case_directories(root: Path = CASES_DIR) -> list[Path]:
    """Every sub directory that is a case candidate.

    Hidden, cache and underscore directories are excluded; that covers ``_drafts``.
    """
    return sorted(
        p
        for p in root.iterdir()
        if p.is_dir()
        and not p.name.startswith((".", "_"))
        and p.name not in {"__pycache__", DRAFTS_DIRNAME}
    )


def load_all(root: Path = CASES_DIR) -> list[LoadedCase]:
    return [load_case(directory) for directory in case_directories(root)]
