"""Unit tests for the /api/chat/stream endpoint (backend/app/presentation/api/chat.py).

`get_chat_use_case` and `require_session` are overridden via
`app.dependency_overrides` so no lifespan/Redis/GCP is needed. `handle_message`
is an async generator method, so the mock's return_value is a real async
generator (not an awaited value). The real `require_session` is exercised by
overriding only `get_session_token_service` with a real SessionTokenService.
"""

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.application.chat_use_case import ChatUseCase
from app.application.session_token_service import SessionTokenService
from app.entities.errors import SessionMessageLimitExceeded
from app.main import app
from app.presentation.api.auth import get_session_token_service, require_session
from app.presentation.api.chat import _sse_frame, get_chat_use_case
from fastapi.testclient import TestClient

client = TestClient(app)


def test_get_chat_use_case_reads_from_request_app_state() -> None:
    sentinel_use_case = AsyncMock(spec=ChatUseCase)
    fake_request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(chat_use_case=sentinel_use_case))
    )

    assert get_chat_use_case(fake_request) is sentinel_use_case


@pytest.fixture(autouse=True)
def _clear_dependency_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def _fake_chunk_stream(chunks: list[str]):
    async def _gen():
        for chunk in chunks:
            yield chunk

    return _gen()


def _override_chat_use_case(chunks: list[str]) -> AsyncMock:
    fake_use_case = AsyncMock(spec=ChatUseCase)
    fake_use_case.handle_message = MagicMock(return_value=_fake_chunk_stream(chunks))
    app.dependency_overrides[get_chat_use_case] = lambda: fake_use_case
    app.dependency_overrides[require_session] = lambda: "sess-1"
    return fake_use_case


def _frames(response) -> list[str]:
    return [frame for frame in response.text.split("\n\n") if frame]


def _post(message="Hello there", **kwargs):
    return client.post("/api/chat/stream", json={"message": message}, **kwargs)


def test_chat_stream_returns_200_and_event_stream_content_type() -> None:
    _override_chat_use_case(["Hello"])

    response = _post()

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    assert response.headers["cache-control"] == "no-cache"


def test_chat_stream_frames_chunks_in_order_and_terminates() -> None:
    fake_use_case = _override_chat_use_case(["Once ", "upon ", "a time"])

    response = _post()

    assert _frames(response) == ["data: Once ", "data: upon ", "data: a time", "data: [DONE]"]
    fake_use_case.handle_message.assert_called_once_with("sess-1", "Hello there")


def test_chat_stream_single_chunk() -> None:
    _override_chat_use_case(["Hello"])

    assert _frames(_post()) == ["data: Hello", "data: [DONE]"]


def test_chat_stream_multiline_chunk_stays_in_one_frame() -> None:
    _override_chat_use_case(["first line\nsecond line", "third"])

    assert _frames(_post()) == [
        "data: first line\ndata: second line",
        "data: third",
        "data: [DONE]",
    ]


def test_chat_stream_empty_stream_only_sends_done() -> None:
    _override_chat_use_case([])

    assert _frames(_post()) == ["data: [DONE]"]


def test_sse_frame_helper() -> None:
    assert _sse_frame("a") == "data: a\n\n"
    assert _sse_frame("a\nb") == "data: a\ndata: b\n\n"


def test_chat_stream_returns_429_when_message_limit_exceeded() -> None:
    fake_use_case = AsyncMock(spec=ChatUseCase)

    async def _limited(session_id, message):
        raise SessionMessageLimitExceeded(session_id)
        yield  # pragma: no cover - makes this an async generator

    fake_use_case.handle_message = MagicMock(side_effect=_limited)
    app.dependency_overrides[get_chat_use_case] = lambda: fake_use_case
    app.dependency_overrides[require_session] = lambda: "sess-1"

    response = _post()

    assert response.status_code == 429
    assert "text/event-stream" not in response.headers["content-type"]


def test_chat_stream_missing_message_returns_422() -> None:
    _override_chat_use_case(["Hello"])

    response = client.post("/api/chat/stream", json={})

    assert response.status_code == 422
    assert any(e["loc"] == ["body", "message"] for e in response.json()["detail"])


def test_chat_stream_wrong_type_for_message_returns_422() -> None:
    _override_chat_use_case(["Hello"])

    assert client.post("/api/chat/stream", json={"message": 42}).status_code == 422


def test_chat_stream_empty_message_returns_422() -> None:
    fake_use_case = _override_chat_use_case(["Hello"])

    assert _post("").status_code == 422
    fake_use_case.handle_message.assert_not_called()


def test_chat_stream_message_over_2000_chars_returns_422() -> None:
    fake_use_case = _override_chat_use_case(["Hello"])

    assert _post("a" * 2001).status_code == 422
    fake_use_case.handle_message.assert_not_called()


def test_chat_stream_message_of_2000_chars_is_accepted() -> None:
    _override_chat_use_case(["Hello"])

    assert _post("a" * 2000).status_code == 200


def test_chat_stream_ignores_session_id_in_body() -> None:
    """session_id was removed from the body; the id must come from the token."""
    fake_use_case = _override_chat_use_case(["Hello"])

    response = client.post("/api/chat/stream", json={"message": "hi", "session_id": "attacker"})

    assert response.status_code == 200
    fake_use_case.handle_message.assert_called_once_with("sess-1", "hi")


# --- real require_session, with a real token service -------------------------


def _real_auth_setup(chunks: list[str]) -> tuple[AsyncMock, SessionTokenService]:
    service = SessionTokenService("fake-signing-key", 60)
    app.dependency_overrides[get_session_token_service] = lambda: service
    fake_use_case = AsyncMock(spec=ChatUseCase)
    fake_use_case.handle_message = MagicMock(return_value=_fake_chunk_stream(chunks))
    app.dependency_overrides[get_chat_use_case] = lambda: fake_use_case
    return fake_use_case, service


def test_chat_stream_without_authorization_header_returns_401() -> None:
    fake_use_case, _ = _real_auth_setup(["Hello"])

    response = _post()

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    fake_use_case.handle_message.assert_not_called()


def test_chat_stream_with_garbage_token_returns_401() -> None:
    fake_use_case, _ = _real_auth_setup(["Hello"])

    response = _post(headers={"Authorization": "Bearer garbage"})

    assert response.status_code == 401
    fake_use_case.handle_message.assert_not_called()


def test_chat_stream_with_valid_token_uses_token_session_id() -> None:
    fake_use_case, service = _real_auth_setup(["Hello"])
    token = service.issue().token

    response = _post(headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert _frames(response) == ["data: Hello", "data: [DONE]"]
    fake_use_case.handle_message.assert_called_once_with(service.verify(token), "Hello there")
