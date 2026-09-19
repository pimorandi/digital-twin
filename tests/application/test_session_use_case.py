"""Unit tests for SessionUseCase; verifier is mocked, token service is real."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.application.session_token_service import SessionTokenService
from app.application.session_use_case import SessionUseCase
from app.entities.errors import HumanCheckFailed
from app.entities.issued_session import IssuedSession
from app.infrastructure.turnstile_verifier import TurnstileVerifier


def test_create_session_issues_token_when_human_check_passes() -> None:
    verifier = AsyncMock(spec=TurnstileVerifier)
    verifier.verify.return_value = True
    token_service = MagicMock(spec=SessionTokenService)
    token_service.issue.return_value = IssuedSession("tok", 60)

    result = asyncio.run(SessionUseCase(verifier, token_service).create_session("cf-token"))

    assert result == IssuedSession("tok", 60)
    verifier.verify.assert_awaited_once_with("cf-token")


def test_create_session_raises_and_issues_nothing_when_check_fails() -> None:
    verifier = AsyncMock(spec=TurnstileVerifier)
    verifier.verify.return_value = False
    token_service = MagicMock(spec=SessionTokenService)

    with pytest.raises(HumanCheckFailed):
        asyncio.run(SessionUseCase(verifier, token_service).create_session("bad"))

    token_service.issue.assert_not_called()
