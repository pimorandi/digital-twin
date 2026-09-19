"""Unit tests for load_settings (backend/app/entities/config.py).

Pure function over os.environ; no external services required. Each test uses
monkeypatch so environment mutations never leak between tests.
"""

from app.entities.config import Settings, load_settings

_ALL_ENV_VARS = [
    "REDIS_URL",
    "SESSION_TTL_SECONDS",
    "HISTORY_GCS_URI",
    "HISTORY_LOCAL_PATH",
    "CHAT_LOG_GCS_URI",
    "GCP_PROJECT_ID",
    "VERTEX_LOCATION",
    "GEMINI_MODEL",
    "MAX_HISTORY_PAIRS",
]


def test_load_settings_uses_defaults_when_env_vars_unset(monkeypatch) -> None:
    for var in _ALL_ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    settings = load_settings()

    assert settings == Settings(
        redis_url="redis://redis:6379/0",
        session_ttl_seconds=3600,
        history_gcs_uri=None,
        history_local_path=None,
        chat_log_gcs_uri=None,
        gcp_project_id=None,
        vertex_location="us-central1",
        gemini_model="gemini-2.5-flash",
        max_history_pairs=10,
    )


def test_load_settings_reads_all_fields_from_env(monkeypatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://fake-host:6380/1")
    monkeypatch.setenv("SESSION_TTL_SECONDS", "60")
    monkeypatch.setenv("HISTORY_GCS_URI", "gs://fake-bucket/fake-path/history.md")
    monkeypatch.setenv("HISTORY_LOCAL_PATH", "/fake/local/history.md")
    monkeypatch.setenv("CHAT_LOG_GCS_URI", "gs://fake-bucket/fake-logs")
    monkeypatch.setenv("GCP_PROJECT_ID", "fake-project")
    monkeypatch.setenv("VERTEX_LOCATION", "fake-region-1")
    monkeypatch.setenv("GEMINI_MODEL", "fake-gemini-model")
    monkeypatch.setenv("MAX_HISTORY_PAIRS", "5")

    settings = load_settings()

    assert settings == Settings(
        redis_url="redis://fake-host:6380/1",
        session_ttl_seconds=60,
        history_gcs_uri="gs://fake-bucket/fake-path/history.md",
        history_local_path="/fake/local/history.md",
        chat_log_gcs_uri="gs://fake-bucket/fake-logs",
        gcp_project_id="fake-project",
        vertex_location="fake-region-1",
        gemini_model="fake-gemini-model",
        max_history_pairs=5,
    )


def test_load_settings_casts_session_ttl_seconds_to_int(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_TTL_SECONDS", "120")

    settings = load_settings()

    assert settings.session_ttl_seconds == 120
    assert isinstance(settings.session_ttl_seconds, int)


def test_load_settings_casts_max_history_pairs_to_int(monkeypatch) -> None:
    monkeypatch.setenv("MAX_HISTORY_PAIRS", "7")

    settings = load_settings()

    assert settings.max_history_pairs == 7
    assert isinstance(settings.max_history_pairs, int)


def test_load_settings_treats_empty_string_history_vars_as_unset(monkeypatch) -> None:
    """Compose passes `${HISTORY_GCS_URI:-}` through as an empty string when the
    .env var is unset, so empty string must be normalized to None, not kept as ''.
    """
    monkeypatch.setenv("HISTORY_GCS_URI", "")
    monkeypatch.setenv("HISTORY_LOCAL_PATH", "")

    settings = load_settings()

    assert settings.history_gcs_uri is None
    assert settings.history_local_path is None


def test_load_settings_treats_empty_string_gcp_project_id_as_unset(monkeypatch) -> None:
    """Same normalization applies to GCP_PROJECT_ID, which is also optional."""
    monkeypatch.setenv("GCP_PROJECT_ID", "")

    settings = load_settings()

    assert settings.gcp_project_id is None


def test_load_settings_treats_empty_string_chat_log_gcs_uri_as_unset(monkeypatch) -> None:
    monkeypatch.setenv("CHAT_LOG_GCS_URI", "")

    settings = load_settings()

    assert settings.chat_log_gcs_uri is None
