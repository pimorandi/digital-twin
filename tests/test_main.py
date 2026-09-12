"""Unit tests for the `lifespan` startup/shutdown hook (backend/app/main.py).

Exercises `lifespan` directly against a throwaway `FastAPI()` instance (never
the `app.main.app` singleton, so these tests can't leak state into
tests/api/test_chat.py). `Redis.from_url`, `storage.Client`, and
`GcsHistoryLoader` are all patched — no real Redis or GCS is required.

The one behavior worth a dedicated test beyond "does it set app.state" is the
conditional construction of `storage.Client()`: it must only be built when
`HISTORY_GCS_URI` is configured, since building it eagerly would require GCP
credentials even for local/dev runs that use the local-file fallback.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.chat_use_case import ChatUseCase
from app.main import lifespan
from fastapi import FastAPI


def _run_lifespan_once(fastapi_app: FastAPI) -> None:
    async def _run() -> None:
        async with lifespan(fastapi_app):
            pass

    asyncio.run(_run())


def test_lifespan_builds_gcs_client_and_loads_history_when_gcs_uri_set(monkeypatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://fake-host:6379/0")
    monkeypatch.setenv("SESSION_TTL_SECONDS", "3600")
    monkeypatch.setenv("HISTORY_GCS_URI", "gs://fake-bucket/fake-path/history.md")
    monkeypatch.delenv("HISTORY_LOCAL_PATH", raising=False)

    fake_redis_client = MagicMock()
    fake_redis_client.aclose = AsyncMock()
    fake_gcs_client = MagicMock()
    fastapi_app = FastAPI()

    with (
        patch("app.main.Redis") as redis_cls,
        patch("app.main.storage") as storage_module,
        patch("app.main.GcsHistoryLoader") as loader_cls,
    ):
        redis_cls.from_url.return_value = fake_redis_client
        storage_module.Client.return_value = fake_gcs_client
        loader_cls.return_value.load.return_value = "# Fake history\nFake content."

        _run_lifespan_once(fastapi_app)

        redis_cls.from_url.assert_called_once_with("redis://fake-host:6379/0")
        storage_module.Client.assert_called_once_with()
        loader_cls.assert_called_once_with(
            fake_gcs_client, "gs://fake-bucket/fake-path/history.md", None
        )
        fake_redis_client.aclose.assert_awaited_once()

    assert isinstance(fastapi_app.state.chat_use_case, ChatUseCase)
    assert fastapi_app.state.professional_history == "# Fake history\nFake content."


def test_lifespan_skips_gcs_client_when_gcs_uri_unset(monkeypatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://fake-host:6379/0")
    monkeypatch.delenv("HISTORY_GCS_URI", raising=False)
    monkeypatch.setenv("HISTORY_LOCAL_PATH", "/fake/local/history.md")

    fake_redis_client = MagicMock()
    fake_redis_client.aclose = AsyncMock()
    fastapi_app = FastAPI()

    with (
        patch("app.main.Redis") as redis_cls,
        patch("app.main.storage") as storage_module,
        patch("app.main.GcsHistoryLoader") as loader_cls,
    ):
        redis_cls.from_url.return_value = fake_redis_client
        loader_cls.return_value.load.return_value = "# Fake local history"

        _run_lifespan_once(fastapi_app)

        storage_module.Client.assert_not_called()
        loader_cls.assert_called_once_with(None, None, "/fake/local/history.md")

    assert fastapi_app.state.professional_history == "# Fake local history"


def test_lifespan_uses_session_ttl_from_settings_for_session_store(monkeypatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://fake-host:6379/0")
    monkeypatch.setenv("SESSION_TTL_SECONDS", "42")
    monkeypatch.setenv("HISTORY_LOCAL_PATH", "/fake/local/history.md")
    monkeypatch.delenv("HISTORY_GCS_URI", raising=False)

    fake_redis_client = MagicMock()
    fake_redis_client.aclose = AsyncMock()
    fastapi_app = FastAPI()

    with (
        patch("app.main.Redis") as redis_cls,
        patch("app.main.storage"),
        patch("app.main.GcsHistoryLoader") as loader_cls,
    ):
        redis_cls.from_url.return_value = fake_redis_client
        loader_cls.return_value.load.return_value = "# Fake local history"

        _run_lifespan_once(fastapi_app)

    chat_use_case: ChatUseCase = fastapi_app.state.chat_use_case
    # ttl_seconds is private on the session store, but it's the one behavior
    # of `lifespan` wiring worth pinning: settings.session_ttl_seconds must
    # reach the RedisSessionStore, not a hardcoded default.
    assert chat_use_case._session_store._ttl_seconds == 42
