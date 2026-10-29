"""Fixtures for the backend BDD scenarios: the FastAPI app runs in-process, offline."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from homeworking.main import create_app
from homeworking.settings import Settings

from .world import ApiWorld


@pytest.fixture
def app(settings: Settings) -> Iterator[FastAPI]:
    return_app = create_app(settings, create_schema=True)
    with TestClient(return_app):  # runs the lifespan (DB schema, wiring) for the scenario
        yield return_app


@pytest.fixture
def api(app: FastAPI) -> Iterator[ApiWorld]:
    # Each scenario is a fresh guest: its own client and therefore its own cookie jar.
    with TestClient(app) as client:
        yield ApiWorld(client)
