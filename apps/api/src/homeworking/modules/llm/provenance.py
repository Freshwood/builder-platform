"""What the prompt provenance of the chat agent and of the pipeline stages have in common: the
fingerprint of a canonical description and the lock file that pins it to a version.

Each side captures its own prompts (``agent/provenance.py``, ``pipeline/provenance.py``); the lock
makes sure that no prompt change ships without a new version and a changelog entry.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


def fingerprint(canonical: Mapping[str, Any]) -> str:
    """Short, stable hash of a JSON-serialisable description."""
    raw = json.dumps(canonical, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class PromptLock:
    """A lock file ``{"version": ..., "fingerprint": ...}`` next to the prompts it guards."""

    path: Path
    version: str
    version_name: str  # e.g. "PROMPT_VERSION", for the messages
    what: str  # e.g. "The prompt", for the messages
    bump_hint: str  # where to bump the version and what to document

    def read(self) -> dict[str, str]:
        return cast(dict[str, str], json.loads(self.path.read_text(encoding="utf-8")))

    def write(self, value: str) -> None:
        lock = {"version": self.version, "fingerprint": value}
        self.path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")

    def record(self, value: str) -> None:
        """``task prompt:lock``: write the fingerprint (refuses without a version bump)."""
        name = self.path.name
        lock = self.read() if self.path.exists() else {}
        if lock.get("fingerprint") == value:
            print(f"{name} is up to date ({self.version}, {value})")
            return
        if lock.get("version") == self.version:
            sys.exit(
                f"{self.what} changed but {self.version_name} is still {self.version}: "
                f"{self.bump_hint}"
            )
        self.write(value)
        print(f"{name} updated: {self.version} -> {value}")


class Once:
    """Computes an expensive value (a fingerprint) once per process."""

    def __init__(self, compute: Callable[[], Awaitable[str]]) -> None:
        self._compute = compute
        self._value: str | None = None

    async def get(self) -> str:
        if self._value is None:
            self._value = await self._compute()
        return self._value
