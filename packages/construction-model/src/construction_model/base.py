"""Shared primitives of the domain model (kept separate to avoid import cycles)."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field

Mm = Annotated[int, Field(description="Length in millimetres")]
ParamValue = int | float | str | bool


class Origin(StrEnum):
    """Who produced a piece of content (relevant for AI Act Art. 50 labelling)."""

    USER = "user"
    ENGINE = "engine"
    AI = "ai"
