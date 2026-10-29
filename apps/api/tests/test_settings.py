"""The settings refuse an unsafe deployment: production is the default environment."""

import pytest
from pydantic import ValidationError

from homeworking.settings import DEV_SECRET, Settings


def _settings(**values: object) -> Settings:
    # No .env file: the developer's own file must not decide the outcome of a test.
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_a_missing_environment_is_production_and_refuses_the_development_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with pytest.raises(ValidationError, match="SESSION_SECRET must be set"):
        _settings(llm_mode="openai", llm_model="some/model")


def test_production_refuses_the_development_secret_even_when_named() -> None:
    with pytest.raises(ValidationError, match="SESSION_SECRET must be set"):
        _settings(environment="production", llm_mode="openai", llm_model="some/model")
    with pytest.raises(ValidationError, match="SESSION_SECRET must be set"):
        _settings(
            environment="production",
            session_secret=DEV_SECRET,
            llm_mode="openai",
            llm_model="some/model",
        )


def test_production_refuses_the_offline_model() -> None:
    with pytest.raises(ValidationError, match="LLM_MODE=test is not allowed"):
        _settings(environment="production", session_secret="a-real-secret", llm_mode="test")


def test_production_accepts_its_own_secret() -> None:
    settings = _settings(
        environment="production",
        session_secret="a-real-secret",
        llm_mode="openai",
        llm_model="some/model",
    )
    assert settings.secure_cookies


@pytest.mark.parametrize("environment", ["development", "test"])
def test_local_environments_keep_the_development_secret(environment: str) -> None:
    settings = _settings(environment=environment, llm_mode="test")
    assert settings.session_secret.get_secret_value() == DEV_SECRET
    assert not settings.secure_cookies


def test_the_environment_variable_selects_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert _settings().environment == "development"


def test_save_design_creates_follows_the_model_mode_by_default() -> None:
    assert _settings(environment="test", llm_mode="test").save_design_creates is True
    live = _settings(
        environment="production",
        session_secret="a-real-secret",
        llm_mode="openai",
        llm_model="some/model",
    )
    assert live.save_design_creates is False


@pytest.mark.parametrize("llm_mode", ["test", "openai"])
@pytest.mark.parametrize("explicit", [True, False])
def test_save_design_creates_can_be_set_explicitly(llm_mode: str, explicit: bool) -> None:
    settings = _settings(
        environment="test",
        llm_mode=llm_mode,
        llm_model="some/model",
        agent_save_design_creates=explicit,
    )
    assert settings.save_design_creates is explicit


def test_save_design_creates_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_SAVE_DESIGN_CREATES", "false")
    assert _settings(environment="test", llm_mode="test").save_design_creates is False
