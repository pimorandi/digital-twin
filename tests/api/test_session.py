"""Unit tests for POST /api/session; the use case is overridden with a mock."""

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.application.session_use_case import SessionUseCase
from app.entities.errors import HumanCheckFailed
from app.entities.issued_session import IssuedSession
from app.main import app
from app.presentation.api.session import get_session_use_case
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def _override(use_case: AsyncMock) -> None:
    app.dependency_overrides[get_session_use_case] = lambda: use_case


def test_get_session_use_case_reads_from_app_state() -> None:
    sentinel = object()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(session_use_case=sentinel)))

    assert get_session_use_case(request) is sentinel


def test_create_session_returns_token_and_expiry() -> None:
    use_case = AsyncMock(spec=SessionUseCase)
    use_case.create_session.return_value = IssuedSession("signed.token", 3600)
    _override(use_case)

    response = client.post("/api/session", json={"turnstile_token": "cf"})

    assert response.status_code == 200
    assert response.json() == {"session_token": "signed.token", "expires_in": 3600}
    use_case.create_session.assert_awaited_once_with("cf")


def test_create_session_returns_403_when_human_check_fails() -> None:
    use_case = AsyncMock(spec=SessionUseCase)
    use_case.create_session.side_effect = HumanCheckFailed("no")
    _override(use_case)

    response = client.post("/api/session", json={"turnstile_token": "cf"})

    assert response.status_code == 403
    assert response.json() == {"detail": "Human verification failed"}


@pytest.mark.parametrize(
    "body",
    [{}, {"turnstile_token": ""}, {"turnstile_token": "a" * 2049}, {"turnstile_token": 5}],
)
def test_create_session_rejects_invalid_token_with_422(body) -> None:
    use_case = AsyncMock(spec=SessionUseCase)
    _override(use_case)

    response = client.post("/api/session", json=body)

    assert response.status_code == 422
    use_case.create_session.assert_not_called()


def test_create_session_accepts_max_length_token() -> None:
    use_case = AsyncMock(spec=SessionUseCase)
    use_case.create_session.return_value = IssuedSession("t", 1)
    _override(use_case)

    assert client.post("/api/session", json={"turnstile_token": "a" * 2048}).status_code == 200
