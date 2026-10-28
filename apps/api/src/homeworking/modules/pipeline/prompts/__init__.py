"""Versioned stage instructions (provenance, see docs/ai/README.md).

Each stage has its own short prompt. A change to a prompt, an output schema or the stage models
changes the stage fingerprint; ``tests/test_stage_prompts.py`` then requires a new
STAGE_PROMPT_VERSION, an updated ``stages.lock`` and an entry in ``docs/ai/PROMPT_CHANGELOG.md``.
"""

from __future__ import annotations

from pathlib import Path

STAGE_PROMPT_VERSION = "2026-10-28.1"

INTAKE = (Path(__file__).parent / "intake.de.md").read_text(encoding="utf-8")
SKELETON = (Path(__file__).parent / "skeleton.de.md").read_text(encoding="utf-8")
