"""Versioned agent instructions (provenance, see docs/ai/README.md).

The system prompt lives in ``system.de.md``. Every change to it, to a tool description or to a
tool's argument schema changes the prompt fingerprint; ``tests/test_prompt_lock.py`` then
requires a new PROMPT_VERSION, an updated ``prompt.lock`` and an entry in
``docs/ai/PROMPT_CHANGELOG.md``.
"""

from __future__ import annotations

from pathlib import Path

PROMPT_VERSION = "2026-10-10.1"

INSTRUCTIONS = (Path(__file__).parent / "system.de.md").read_text(encoding="utf-8")
