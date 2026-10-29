"""The lock helper shared by the agent and the stage provenance."""

import asyncio
from pathlib import Path

import pytest

from homeworking.modules.agent import provenance as agent
from homeworking.modules.llm.provenance import Once, PromptLock, fingerprint
from homeworking.modules.pipeline import provenance as stages


def _lock(tmp_path: Path, version: str = "v2") -> PromptLock:
    return PromptLock(
        path=tmp_path / "x.lock",
        version=version,
        version_name="X_VERSION",
        what="The prompt",
        bump_hint="bump it.",
    )


def test_the_fingerprint_ignores_key_order() -> None:
    assert fingerprint({"a": 1, "b": [2]}) == fingerprint({"b": [2], "a": 1})
    assert len(fingerprint({})) == 16


@pytest.mark.parametrize("module", [agent, stages])
def test_the_lock_files_keep_their_format(module: object) -> None:
    lock: PromptLock = module.LOCK  # type: ignore[attr-defined]
    text = lock.path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    current = lock.read()
    # Writing the recorded fingerprint again reproduces the file byte for byte.
    assert (
        text
        == f'{{\n  "version": "{lock.version}",\n  "fingerprint": "{current["fingerprint"]}"\n}}\n'
    )
    assert module.read_lock() == current  # type: ignore[attr-defined]


def test_a_new_lock_is_written(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    lock = _lock(tmp_path)
    lock.record("abc")
    assert lock.read() == {"version": "v2", "fingerprint": "abc"}
    assert "x.lock updated: v2 -> abc" in capsys.readouterr().out


def test_an_unchanged_fingerprint_is_up_to_date(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lock = _lock(tmp_path)
    lock.write("abc")
    lock.record("abc")
    assert "x.lock is up to date (v2, abc)" in capsys.readouterr().out


def test_a_changed_fingerprint_needs_a_new_version(tmp_path: Path) -> None:
    _lock(tmp_path, "v1").write("abc")
    with pytest.raises(SystemExit) as raised:
        _lock(tmp_path, "v1").record("def")
    assert str(raised.value) == "The prompt changed but X_VERSION is still v1: bump it."
    assert _lock(tmp_path).read()["fingerprint"] == "abc"  # not overwritten
    _lock(tmp_path, "v2").record("def")
    assert _lock(tmp_path).read() == {"version": "v2", "fingerprint": "def"}


def test_once_computes_a_value_a_single_time() -> None:
    calls: list[int] = []

    async def compute() -> str:
        calls.append(1)
        return "v"

    once = Once(compute)
    assert asyncio.run(once.get()) == "v"
    assert asyncio.run(once.get()) == "v"
    assert len(calls) == 1
