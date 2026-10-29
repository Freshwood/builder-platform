"""Bind the backend Gherkin scenarios (German) to the step definitions."""

from pathlib import Path

from pytest_bdd import scenarios

from .steps.api_steps import *  # noqa: F403

scenarios(str(Path(__file__).parent / "features"))
