"""Unit tests for RedisSessionStore (backend/app/persistence/session_store.py).

The redis.asyncio.Redis client is mocked; no real Redis instance is required.
Coroutines are driven with `asyncio.run` from plain sync test functions rather
than an async test framework, since pytest-asyncio is not a declared
dependency of this repo.
"""

import asyncio
from unittest.mock import AsyncMock

from app.persistence.session_store import RedisSessionStore


def test_increment_message_count_calls_incr_with_namespaced_key() -> None:
    client = AsyncMock()
    client.incr.return_value = 1
    store = RedisSessionStore(client, ttl_seconds=3600)

    asyncio.run(store.increment_message_count("abc123"))

    client.incr.assert_awaited_once_with("session:abc123:message_count")


def test_increment_message_count_returns_incr_result() -> None:
    client = AsyncMock()
    client.incr.return_value = 5
    store = RedisSessionStore(client, ttl_seconds=3600)

    result = asyncio.run(store.increment_message_count("abc123"))

    assert result == 5


def test_increment_message_count_sets_expiry_with_configured_ttl() -> None:
    client = AsyncMock()
    client.incr.return_value = 1
    store = RedisSessionStore(client, ttl_seconds=1800)

    asyncio.run(store.increment_message_count("abc123"))

    client.expire.assert_awaited_once_with("session:abc123:message_count", 1800)


def test_increment_message_count_uses_distinct_keys_per_session() -> None:
    client = AsyncMock()
    client.incr.return_value = 1
    store = RedisSessionStore(client, ttl_seconds=60)

    asyncio.run(store.increment_message_count("session-a"))
    asyncio.run(store.increment_message_count("session-b"))

    incr_calls = [call.args[0] for call in client.incr.await_args_list]
    assert incr_calls == [
        "session:session-a:message_count",
        "session:session-b:message_count",
    ]
