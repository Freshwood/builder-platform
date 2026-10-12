"""Run the design corpus: every case is built and must satisfy every invariant in ``corpus.check``.

``corpus.py`` holds the invariants and the case generators, ``corpus_designs.py`` the free-form
designs and the bug regressions. A failing case names its rule and the detail, so a report reads
like a bug description ("drawing_shows_all_parts: Ansicht 'front' zeigt 11 Teile, ...").
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# --import-mode=importlib does not add this directory to sys.path (see corpus.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import Case, build_result, cases, check
from corpus_designs import DESIGNS, DESIGNS_FROM_BUGS, EXTRA_DESIGNS

from calc_engine.engine import DesignRejectedError, default_engine
from construction_model.drawing import Drawing, Primitive
from construction_model.model import ConstructionResult

#: Engine defects the corpus has found and that are not fixed yet. Case-name prefix -> reason.
#: A matching case is expected to fail (``xfail(strict=True)``): the suite stays green, the defect
#: stays documented, and the moment it is fixed the case XPASSes and fails the run until the
#: entry is removed. Never add an entry to silence a failure you have not understood.
KNOWN_DEFECTS: dict[str, str] = {}

_ENGINE = default_engine()
_CASES = cases()


def _marks(case: Case) -> list[pytest.MarkDecorator]:
    for prefix, reason in KNOWN_DEFECTS.items():
        if case.name.startswith(prefix):
            return [pytest.mark.xfail(strict=True, reason=reason)]
    return []


@pytest.mark.parametrize(
    "case",
    [pytest.param(case, id=case.name, marks=_marks(case)) for case in _CASES],
)
def test_corpus_case_satisfies_every_invariant(case: Case) -> None:
    if case.expect_rejection is not None:
        with pytest.raises(DesignRejectedError, match=case.expect_rejection):
            build_result(case, _ENGINE)
        return
    try:
        result = build_result(case, _ENGINE)
    except DesignRejectedError as error:
        pytest.fail(f"{case.name} ({case.source}) wurde von der Engine abgelehnt: {error}")
    violations = check(result, case)
    assert not violations, "\n".join(
        f"[{v.rule}] {case.name} (params={dict(case.params)}): {v.detail}" for v in violations
    )


def test_corpus_is_non_trivial() -> None:
    names = [case.name for case in _CASES]
    assert len(names) > 100
    assert len(set(names)) == len(names), "Fallnamen müssen eindeutig sein"
    sources = {case.source for case in _CASES}
    assert any(source.startswith("template:") for source in sources)
    assert any(source.startswith("pack:") for source in sources)
    for key in EXTRA_DESIGNS:
        assert f"design:{key}" in sources
    assert len(DESIGNS_FROM_BUGS) >= 2
    for key in DESIGNS_FROM_BUGS:
        assert f"bug:{key}" in sources
        assert f"bug:{key}#reported" in names


def test_corpus_is_deterministic() -> None:
    again = cases()
    assert [(c.name, dict(c.params)) for c in again] == [(c.name, dict(c.params)) for c in _CASES]


def test_every_free_form_design_is_in_the_corpus() -> None:
    covered = {id(design) for design in EXTRA_DESIGNS.values()}
    covered |= {id(bug.design) for bug in DESIGNS_FROM_BUGS.values() if bug.design is not None}
    assert {id(design) for design in DESIGNS} <= covered


def test_a_rejection_case_expects_the_engine_to_say_no() -> None:
    """The harness itself: a design the engine must reject is a case, not a crash."""
    from corpus_designs import PODIUM

    from construction_model.assembly import AssemblyDesign

    case = Case(
        "harness:too-wide",
        AssemblyDesign.model_validate(PODIUM),
        {"width_mm": 10**9},
        expect_rejection=".",
    )
    with pytest.raises(DesignRejectedError):
        build_result(case, _ENGINE)


def _reported_podium() -> tuple[Case, ConstructionResult]:
    case = next(c for c in _CASES if c.name == "bug:podium#reported")
    return case, build_result(case, _ENGINE)


@pytest.mark.parametrize(
    ("tamper", "rule"),
    [
        ("drop_cut_line", "part_accounted_for"),
        ("drop_solid", "solids_match_components"),
        ("drop_drawn_part", "drawing_shows_all_parts"),
        ("bump_cut_count", "cut_quantity"),
        ("stretch_cut", "piece_is_planned"),
        ("blank_drawing", "drawing_not_blank"),
    ],
)
def test_check_catches_a_tampered_result(tamper: str, rule: str) -> None:
    """The invariants must fail on a result that is wrong, or a green corpus proves nothing."""
    case, result = _reported_podium()
    assert check(result, case) == []
    cut = result.cut_list
    front = next(d for d in result.drawings if d.view == "front")
    filled = [p for p in front.primitives if p.kind in {"polygon", "rect"}]
    other = [p for p in front.primitives if p.kind not in {"polygon", "rect"}]
    update: dict[str, object]
    match tamper:
        case "drop_cut_line":
            update = {"cut_list": cut[1:]}
        case "drop_solid":
            update = {"solids": result.solids[1:]}
        case "drop_drawn_part":
            update = {"drawings": _with_view(result, front, other + filled[1:])}
        case "bump_cut_count":
            update = {"cut_list": [cut[0].model_copy(update={"count": cut[0].count + 1}), *cut[1:]]}
        case "stretch_cut":
            update = {
                "cut_list": [
                    cut[0].model_copy(update={"length_mm": cut[0].length_mm + 7}),
                    *cut[1:],
                ]
            }
        case _:
            update = {"drawings": _with_view(result, front, other)}
    rules = {v.rule for v in check(result.model_copy(update=update), case)}
    assert rule in rules, f"{tamper}: erwartet {rule}, gefunden {sorted(rules)}"


def _with_view(
    result: ConstructionResult, view: Drawing, primitives: list[Primitive]
) -> list[Drawing]:
    return [
        d.model_copy(update={"primitives": primitives}) if d is view else d for d in result.drawings
    ]
