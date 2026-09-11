"""Unit tests for the /api/chat/stream endpoint (backend/app/presentation/api/chat.py).

The real `get_chat_use_case` dependency reads `request.app.state.chat_use_case`,
which is only populated by the app's `lifespan` (which needs a real Redis
connection). Per CLAUDE.md's unit-test convention, these tests instead override
that dependency with a fake/mocked `ChatUseCase` so no external services are
required.
"""

from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
from app.application.chat_use_case import ChatUseCase
from app.main import app
from app.presentation.api.chat import get_chat_use_case
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides() -> Iterator[None]:
    """Ensure overrides never leak between tests/modules."""
    yield
    app.dependency_overrides.clear()


def _override_chat_use_case(count: int) -> AsyncMock:
    fake_use_case = AsyncMock(spec=ChatUseCase)
    fake_use_case.handle_message.return_value = count
    app.dependency_overrides[get_chat_use_case] = lambda: fake_use_case
    return fake_use_case


def test_chat_stream_returns_200_and_event_stream_content_type() -> None:
    _override_chat_use_case(1)

    response = client.post(
        "/api/chat/stream",
        json={"session_id": "abc123", "message": "Hello there"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"


def test_chat_stream_body_contains_count_frame_and_terminates() -> None:
    _override_chat_use_case(1)

    response = client.post(
        "/api/chat/stream",
        json={"session_id": "abc123", "message": "Hello there"},
    )

    body = response.text
    frames = [frame for frame in body.split("\n\n") if frame]

    assert frames == ["data: 1", "data: [DONE]"]


def test_chat_stream_body_reflects_use_case_count() -> None:
    """The streamed count must be whatever the use case returns, not hardcoded."""
    fake_use_case = _override_chat_use_case(42)

    response = client.post(
        "/api/chat/stream",
        json={"session_id": "abc123", "message": "Hello there"},
    )

    body = response.text
    frames = [frame for frame in body.split("\n\n") if frame]

    assert frames == ["data: 42", "data: [DONE]"]
    fake_use_case.handle_message.assert_awaited_once_with("abc123", "Hello there")


def test_chat_stream_missing_message_returns_422() -> None:
    _override_chat_use_case(1)

    response = client.post(
        "/api/chat/stream",
        json={"session_id": "abc123"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(error["loc"] == ["body", "message"] for error in detail)


def test_chat_stream_missing_session_id_returns_422() -> None:
    _override_chat_use_case(1)

    response = client.post(
        "/api/chat/stream",
        json={"message": "Hello there"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(error["loc"] == ["body", "session_id"] for error in detail)


def test_chat_stream_empty_body_returns_422() -> None:
    _override_chat_use_case(1)

    response = client.post("/api/chat/stream", json={})

    assert response.status_code == 422


def test_chat_stream_wrong_type_for_message_returns_422() -> None:
    _override_chat_use_case(1)

    response = client.post(
        "/api/chat/stream",
        json={"session_id": "abc123", "message": 42},
    )

    assert response.status_code == 422
