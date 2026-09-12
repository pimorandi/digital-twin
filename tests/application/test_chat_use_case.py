"""Unit tests for ChatUseCase (backend/app/application/chat_use_case.py).

RedisSessionStore is mocked; no real Redis instance is required. This class is
only exercised indirectly today (via tests/api/test_chat.py, which overrides
the FastAPI dependency with a fully mocked ChatUseCase). That means the real
`handle_message` body has zero direct coverage, so it gets a small dedicated
unit test here.
"""

import asyncio
from unittest.mock import AsyncMock

from app.application.chat_use_case import ChatUseCase
from app.persistence.session_store import RedisSessionStore


def test_handle_message_delegates_to_session_store() -> None:
    session_store = AsyncMock(spec=RedisSessionStore)
    session_store.increment_message_count.return_value = 1
    use_case = ChatUseCase(session_store)

    asyncio.run(use_case.handle_message("abc123", "Hello there"))

    session_store.increment_message_count.assert_awaited_once_with("abc123")


def test_handle_message_returns_session_store_result() -> None:
    session_store = AsyncMock(spec=RedisSessionStore)
    session_store.increment_message_count.return_value = 7
    use_case = ChatUseCase(session_store)

    result = asyncio.run(use_case.handle_message("abc123", "Hello there"))

    assert result == 7


def test_handle_message_ignores_message_content() -> None:
    """The message text isn't forwarded to the session store; only the session
    id drives the (currently message-count-only) behavior."""
    session_store = AsyncMock(spec=RedisSessionStore)
    session_store.increment_message_count.return_value = 1
    use_case = ChatUseCase(session_store)

    asyncio.run(use_case.handle_message("abc123", "first message"))
    asyncio.run(use_case.handle_message("abc123", "a completely different message"))

    assert session_store.increment_message_count.await_args_list == [
        (("abc123",), {}),
        (("abc123",), {}),
    ]
