"""Unit tests for RedisSessionStore (backend/app/persistence/session_store.py).

The redis.asyncio.Redis client is mocked; no real Redis instance is required.
Coroutines are driven with `asyncio.run` from plain sync test functions rather
than an async test framework, since pytest-asyncio is not a declared
dependency of this repo.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from app.entities.chat_turn import ChatTurn
from app.persistence.session_store import RedisSessionStore


def test_increment_message_count_calls_incr_with_namespaced_key() -> None:
    client = AsyncMock()
    client.incr.return_value = 1
    store = RedisSessionStore(client, ttl_seconds=3600, max_history_pairs=10)

    asyncio.run(store.increment_message_count("abc123"))

    client.incr.assert_awaited_once_with("session:abc123:message_count")


def test_increment_message_count_returns_incr_result() -> None:
    client = AsyncMock()
    client.incr.return_value = 5
    store = RedisSessionStore(client, ttl_seconds=3600, max_history_pairs=10)

    result = asyncio.run(store.increment_message_count("abc123"))

    assert result == 5


def test_increment_message_count_sets_expiry_with_configured_ttl() -> None:
    client = AsyncMock()
    client.incr.return_value = 1
    store = RedisSessionStore(client, ttl_seconds=1800, max_history_pairs=10)

    asyncio.run(store.increment_message_count("abc123"))

    client.expire.assert_awaited_once_with("session:abc123:message_count", 1800)


def test_increment_message_count_uses_distinct_keys_per_session() -> None:
    client = AsyncMock()
    client.incr.return_value = 1
    store = RedisSessionStore(client, ttl_seconds=60, max_history_pairs=10)

    asyncio.run(store.increment_message_count("session-a"))
    asyncio.run(store.increment_message_count("session-b"))

    incr_calls = [call.args[0] for call in client.incr.await_args_list]
    assert incr_calls == [
        "session:session-a:message_count",
        "session:session-b:message_count",
    ]


def _client_with_pipeline() -> tuple[MagicMock, MagicMock]:
    """redis.asyncio: `client.pipeline()` is a sync call returning an async context
    manager; queued commands are sync, `execute` is awaited."""
    pipe = MagicMock()
    pipe.execute = AsyncMock()
    client = MagicMock()
    client.pipeline.return_value.__aenter__ = AsyncMock(return_value=pipe)
    client.pipeline.return_value.__aexit__ = AsyncMock(return_value=False)
    return client, pipe


def test_append_turn_pushes_json_encoded_turn_to_namespaced_key() -> None:
    client, pipe = _client_with_pipeline()
    store = RedisSessionStore(client, ttl_seconds=3600, max_history_pairs=10)

    asyncio.run(store.append_turn("abc123", ChatTurn(role="user", text="hello there")))

    client.pipeline.assert_called_once_with(transaction=True)
    pipe.rpush.assert_called_once_with(
        "session:abc123:messages", json.dumps({"role": "user", "text": "hello there"})
    )


def test_append_turn_trims_list_to_max_history_pairs() -> None:
    client, pipe = _client_with_pipeline()
    store = RedisSessionStore(client, ttl_seconds=3600, max_history_pairs=3)

    asyncio.run(store.append_turn("abc123", ChatTurn(role="user", text="x")))

    pipe.ltrim.assert_called_once_with("session:abc123:messages", -6, -1)


def test_append_turn_sets_expiry_with_configured_ttl() -> None:
    client, pipe = _client_with_pipeline()
    store = RedisSessionStore(client, ttl_seconds=1800, max_history_pairs=10)

    asyncio.run(store.append_turn("abc123", ChatTurn(role="model", text="hi!")))

    pipe.expire.assert_called_once_with("session:abc123:messages", 1800)


def test_append_turn_executes_pipeline_and_queues_commands_in_order() -> None:
    client, pipe = _client_with_pipeline()
    store = RedisSessionStore(client, ttl_seconds=60, max_history_pairs=2)

    asyncio.run(store.append_turn("abc123", ChatTurn(role="model", text="hi!")))

    pipe.execute.assert_awaited_once_with()
    queued = [c[0] for c in pipe.method_calls if c[0] != "execute"]
    assert queued == ["rpush", "ltrim", "expire"]


def test_get_history_returns_chat_turns_decoded_from_json() -> None:
    client = AsyncMock()
    client.lrange.return_value = [
        json.dumps({"role": "user", "text": "hello there"}),
        json.dumps({"role": "model", "text": "hi!"}),
    ]
    store = RedisSessionStore(client, ttl_seconds=3600, max_history_pairs=10)

    history = asyncio.run(store.get_history("abc123"))

    assert history == [
        ChatTurn(role="user", text="hello there"),
        ChatTurn(role="model", text="hi!"),
    ]


def test_get_history_reads_namespaced_key_bounded_by_max_history_pairs() -> None:
    client = AsyncMock()
    client.lrange.return_value = []
    store = RedisSessionStore(client, ttl_seconds=3600, max_history_pairs=3)

    asyncio.run(store.get_history("abc123"))

    client.lrange.assert_awaited_once_with("session:abc123:messages", -6, -1)


def test_get_history_returns_empty_list_when_no_messages_stored() -> None:
    client = AsyncMock()
    client.lrange.return_value = []
    store = RedisSessionStore(client, ttl_seconds=3600, max_history_pairs=10)

    history = asyncio.run(store.get_history("abc123"))

    assert history == []
