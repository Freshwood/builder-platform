"""The dimensions printed in the drawings agree with the solids, for every buildable corpus case.

``test_corpus.py`` checks that every part is drawn; ``intent.view_consistency`` checks the numbers
on the drawing: each printed dimension equals the real extent of the solids and the views agree
with each other. A case the engine rejects is not buildable and is reported by ``test_corpus.py``;
it is skipped here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# --import-mode=importlib does not add this directory to sys.path (see corpus.py).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import Case, build_result, cases

from calc_engine.assembly.intent import view_consistency
from calc_engine.engine import DesignRejectedError, default_engine

_ENGINE = default_engine()
_CASES = [case for case in cases() if case.expect_rejection is None]


@pytest.mark.parametrize("case", [pytest.param(case, id=case.name) for case in _CASES])
def test_corpus_case_has_consistent_views(case: Case) -> None:
    try:
        result = build_result(case, _ENGINE)
    except DesignRejectedError:
        pytest.skip("not buildable (reported by test_corpus.py)")
    found = view_consistency(result)
    assert not found, "\n".join(
        f"[{v.rule}] {case.name} (params={dict(case.params)}): {v.detail}" for v in found
    )
