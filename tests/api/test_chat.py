"""Unit tests for the /api/chat/stream endpoint (backend/app/api/chat.py).

This is a thin skeleton with no external dependencies (no redis, LLM, or GCS
history loading yet), so these tests only exercise the FastAPI wiring and the
canned SSE response — nothing to mock.
"""

from app.api.chat import FIXED_RESPONSE
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_chat_stream_returns_200_and_event_stream_content_type() -> None:
    response = client.post(
        "/api/chat/stream",
        json={"session_id": "abc123", "message": "Hello there"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"


def test_chat_stream_body_contains_expected_word_frames_and_terminates() -> None:
    response = client.post(
        "/api/chat/stream",
        json={"session_id": "abc123", "message": "Hello there"},
    )

    body = response.text
    frames = [frame for frame in body.split("\n\n") if frame]

    expected_words = FIXED_RESPONSE.split(" ")
    expected_frames = [f"data: {word} " for word in expected_words] + ["data: [DONE]"]

    assert frames == expected_frames


def test_chat_stream_missing_message_returns_422() -> None:
    response = client.post(
        "/api/chat/stream",
        json={"session_id": "abc123"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(error["loc"] == ["body", "message"] for error in detail)


def test_chat_stream_missing_session_id_returns_422() -> None:
    response = client.post(
        "/api/chat/stream",
        json={"message": "Hello there"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(error["loc"] == ["body", "session_id"] for error in detail)


def test_chat_stream_empty_body_returns_422() -> None:
    response = client.post("/api/chat/stream", json={})

    assert response.status_code == 422


def test_chat_stream_wrong_type_for_message_returns_422() -> None:
    response = client.post(
        "/api/chat/stream",
        json={"session_id": "abc123", "message": 42},
    )

    assert response.status_code == 422
