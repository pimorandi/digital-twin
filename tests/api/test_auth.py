"""Unit tests for the auth dependencies (presentation/api/auth.py)."""

from types import SimpleNamespace

import pytest
from app.application.session_token_service import SessionTokenService
from app.entities.errors import InvalidSessionToken
from app.presentation.api.auth import get_session_token_service, require_session


def _service() -> SessionTokenService:
    return SessionTokenService("fake-key", 60)


def test_get_session_token_service_reads_app_state() -> None:
    sentinel = object()
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(session_token_service=sentinel))
    )

    assert get_session_token_service(request) is sentinel


@pytest.mark.parametrize("header", [None, "", "Bearer", "Bearer ", "Basic abc", "abc"])
def test_require_session_rejects_missing_or_non_bearer(header) -> None:
    with pytest.raises(InvalidSessionToken):
        require_session(header, _service())


def test_require_session_accepts_valid_bearer_case_insensitive() -> None:
    service = _service()
    token = service.issue().token

    assert require_session(f"bearer {token}", service) == service.verify(token)


def test_require_session_propagates_verify_failure() -> None:
    with pytest.raises(InvalidSessionToken):
        require_session("Bearer garbage", _service())
