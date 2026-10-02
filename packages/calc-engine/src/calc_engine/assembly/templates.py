"""Curated design templates (trust level ``template``, ADR-0004)."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources

from pydantic import BaseModel, ConfigDict

from construction_model.assembly import AssemblyDesign


class DesignTemplate(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    title: str
    description: str
    keywords: list[str]
    design: AssemblyDesign


@cache
def templates() -> dict[str, DesignTemplate]:
    folder = resources.files("calc_engine").joinpath("data/templates")
    out: dict[str, DesignTemplate] = {}
    for entry in sorted(folder.iterdir(), key=lambda e: e.name):
        if entry.name.endswith(".json"):
            template = DesignTemplate.model_validate(json.loads(entry.read_text("utf-8")))
            out[template.key] = template
    return out


def template(key: str) -> DesignTemplate:
    try:
        return templates()[key]
    except KeyError:
        raise KeyError(f"Unknown design template '{key}'") from None
