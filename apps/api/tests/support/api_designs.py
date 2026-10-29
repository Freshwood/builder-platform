"""Designs for API tests: the ones the offline planner drafts, as JSON for requests."""

from __future__ import annotations

from typing import Any

from homeworking.construction_model.assembly import AssemblyDesign
from homeworking.modules.agent.offline import offline_designs


def design(key: str) -> AssemblyDesign:
    return next(d.design for d in offline_designs() if d.key == key)


def design_json(key: str) -> dict[str, Any]:
    return design(key).model_dump(mode="json", exclude_defaults=True)


def create_body(key: str, title: str, **params: Any) -> dict[str, Any]:
    """Body of ``POST /api/projects`` for an offline design."""
    return {"title": title, "design": design_json(key), "params": params}
