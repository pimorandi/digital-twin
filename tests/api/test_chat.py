"""Unit tests for the /api/chat/stream endpoint (backend/app/presentation/api/chat.py).

The real `get_chat_use_case` dependency reads `request.app.state.chat_use_case`,
which is only populated by the app's `lifespan` (which needs a real Redis/GCP
connection). Per CLAUDE.md's unit-test convention, these tests instead override
that dependency with a fake/mocked `ChatUseCase` so no external services are
required.

`ChatUseCase.handle_message` is an async *generator* method (it contains a
`yield`), so calling it returns an async generator object directly rather than
a coroutine — the mock's `handle_message` attribute is therefore given a
plain (non-async) `return_value` of a real async generator, not an awaited
return value.
"""

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.application.chat_use_case import ChatUseCase
from app.main import app
from app.presentation.api.chat import get_chat_use_case
from fastapi.testclient import TestClient

client = TestClient(app)


def test_get_chat_use_case_reads_from_request_app_state() -> None:
    """The real dependency (bypassed by every route test above via
    dependency_overrides) is just a one-line accessor onto app.state, wired up
    by lifespan. Exercised directly here with a fake Request-like object so it
    isn't left with zero coverage."""
    sentinel_use_case = AsyncMock(spec=ChatUseCase)
    fake_request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(chat_use_case=sentinel_use_case))
    )

    result = get_chat_use_case(fake_request)

    assert result is sentinel_use_case


@pytest.fixture(autouse=True)
def _clear_dependency_overrides() -> Iterator[None]:
    """Ensure overrides never leak between tests/modules."""
    yield
    app.dependency_overrides.clear()


def _fake_chunk_stream(chunks: list[str]):
    async def _gen():
        for chunk in chunks:
            yield chunk

    return _gen()


def _override_chat_use_case(chunks: list[str]) -> AsyncMock:
    fake_use_case = AsyncMock(spec=ChatUseCase)
    fake_use_case.handle_message.return_value = _fake_chunk_stream(chunks)
    app.dependency_overrides[get_chat_use_case] = lambda: fake_use_case
    return fake_use_case


def test_chat_stream_returns_200_and_event_stream_content_type() -> None:
    _override_chat_use_case(["Hello"])

    response = client.post(
        "/api/chat/stream",
        json={"session_id": "abc123", "message": "Hello there"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"


def test_chat_stream_body_contains_chunk_frame_and_terminates() -> None:
    _override_chat_use_case(["Hello"])

    response = client.post(
        "/api/chat/stream",
        json={"session_id": "abc123", "message": "Hello there"},
    )

    body = response.text
    frames = [frame for frame in body.split("\n\n") if frame]

    assert frames == ["data: Hello", "data: [DONE]"]


def test_chat_stream_body_reflects_use_case_chunks_in_order() -> None:
    """The streamed frames must be whatever the use case yields, not hardcoded,
    and must preserve chunk order."""
    fake_use_case = _override_chat_use_case(["Once ", "upon ", "a time"])

    response = client.post(
        "/api/chat/stream",
        json={"session_id": "abc123", "message": "Hello there"},
    )

    body = response.text
    frames = [frame for frame in body.split("\n\n") if frame]

    assert frames == ["data: Once ", "data: upon ", "data: a time", "data: [DONE]"]
    fake_use_case.handle_message.assert_called_once_with("abc123", "Hello there")


def test_chat_stream_splits_multiline_chunk_into_multiple_data_lines_within_one_frame() -> None:
    """A chunk containing an embedded newline must become two `data:` lines
    within a single SSE frame (multi-line-safe framing), not corrupt the
    stream by leaving a bare newline that a naive client would read as the
    frame terminator."""
    _override_chat_use_case(["first line\nsecond line"])

    response = client.post(
        "/api/chat/stream",
        json={"session_id": "abc123", "message": "Hello there"},
    )

    body = response.text
    frames = [frame for frame in body.split("\n\n") if frame]

    assert frames == ["data: first line\ndata: second line", "data: [DONE]"]


def test_chat_stream_handles_no_chunks_and_still_terminates() -> None:
    _override_chat_use_case([])

    response = client.post(
        "/api/chat/stream",
        json={"session_id": "abc123", "message": "Hello there"},
    )

    body = response.text
    frames = [frame for frame in body.split("\n\n") if frame]

    assert frames == ["data: [DONE]"]


def test_chat_stream_missing_message_returns_422() -> None:
    _override_chat_use_case(["Hello"])

    response = client.post(
        "/api/chat/stream",
        json={"session_id": "abc123"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(error["loc"] == ["body", "message"] for error in detail)


def test_chat_stream_missing_session_id_returns_422() -> None:
    _override_chat_use_case(["Hello"])

    response = client.post(
        "/api/chat/stream",
        json={"message": "Hello there"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(error["loc"] == ["body", "session_id"] for error in detail)


def test_chat_stream_empty_body_returns_422() -> None:
    _override_chat_use_case(["Hello"])

    response = client.post("/api/chat/stream", json={})

    assert response.status_code == 422


def test_chat_stream_wrong_type_for_message_returns_422() -> None:
    _override_chat_use_case(["Hello"])

    response = client.post(
        "/api/chat/stream",
        json={"session_id": "abc123", "message": 42},
    )

    assert response.status_code == 422
