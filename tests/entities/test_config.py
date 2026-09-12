"""Unit tests for load_settings (backend/app/entities/config.py).

Pure function over os.environ; no external services required. Each test uses
monkeypatch so environment mutations never leak between tests.
"""

from app.entities.config import Settings, load_settings


def test_load_settings_uses_defaults_when_env_vars_unset(monkeypatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("SESSION_TTL_SECONDS", raising=False)
    monkeypatch.delenv("HISTORY_GCS_URI", raising=False)
    monkeypatch.delenv("HISTORY_LOCAL_PATH", raising=False)

    settings = load_settings()

    assert settings == Settings(
        redis_url="redis://redis:6379/0",
        session_ttl_seconds=3600,
        history_gcs_uri=None,
        history_local_path=None,
    )


def test_load_settings_reads_all_fields_from_env(monkeypatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://fake-host:6380/1")
    monkeypatch.setenv("SESSION_TTL_SECONDS", "60")
    monkeypatch.setenv("HISTORY_GCS_URI", "gs://fake-bucket/fake-path/history.md")
    monkeypatch.setenv("HISTORY_LOCAL_PATH", "/fake/local/history.md")

    settings = load_settings()

    assert settings == Settings(
        redis_url="redis://fake-host:6380/1",
        session_ttl_seconds=60,
        history_gcs_uri="gs://fake-bucket/fake-path/history.md",
        history_local_path="/fake/local/history.md",
    )


def test_load_settings_casts_session_ttl_seconds_to_int(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_TTL_SECONDS", "120")

    settings = load_settings()

    assert settings.session_ttl_seconds == 120
    assert isinstance(settings.session_ttl_seconds, int)


def test_load_settings_treats_empty_string_history_vars_as_unset(monkeypatch) -> None:
    """Compose passes `${HISTORY_GCS_URI:-}` through as an empty string when the
    .env var is unset, so empty string must be normalized to None, not kept as ''.
    """
    monkeypatch.setenv("HISTORY_GCS_URI", "")
    monkeypatch.setenv("HISTORY_LOCAL_PATH", "")

    settings = load_settings()

    assert settings.history_gcs_uri is None
    assert settings.history_local_path is None
