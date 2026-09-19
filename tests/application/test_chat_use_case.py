"""Unit tests for ChatUseCase (backend/app/application/chat_use_case.py).

RedisSessionStore and GeminiClient are both mocked; no real Redis or GCP call
is made. `handle_message` is an async generator, so it's driven with
`asyncio.run` from plain sync test functions (matching the pattern already
established in this repo's other async tests), collecting all yielded chunks
via a small helper.

GeminiClient.generate_stream is an async *generator* method (it contains a
`yield`), so calling it returns an async generator object directly rather than
a coroutine — it must therefore be mocked as a plain MagicMock whose
return_value is an async generator, not an AsyncMock (which would require an
extra `await` the real call site never performs).
"""

import asyncio
import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.application.chat_use_case import ChatUseCase
from app.entities.chat_log_record import ChatLogRecord
from app.entities.chat_turn import ChatTurn
from app.entities.errors import SessionMessageLimitExceeded
from app.entities.prompts import render_system_instruction
from app.infrastructure.gemini_client import GeminiClient
from app.persistence.session_store import RedisSessionStore

FAKE_HISTORY_DOC = "# Fake history\n- Fake Corp, Fake Role, 2020-2022"


def _fake_stream(chunks: list[str]):
    async def _gen():
        for chunk in chunks:
            yield chunk

    return _gen()


def _make_use_case(
    stream_chunks: list[str] | None = None,
    stored_history: list[ChatTurn] | None = None,
    chat_log_writer: MagicMock | None = None,
    message_count: int = 1,
    max_messages: int = 30,
) -> tuple[ChatUseCase, AsyncMock, MagicMock]:
    session_store = AsyncMock(spec=RedisSessionStore)
    session_store.increment_message_count.return_value = message_count
    session_store.get_history.return_value = stored_history or []

    gemini_client = MagicMock(spec=GeminiClient)
    gemini_client.generate_stream = MagicMock(return_value=_fake_stream(stream_chunks or []))

    use_case = ChatUseCase(
        session_store, gemini_client, FAKE_HISTORY_DOC, max_messages, chat_log_writer
    )
    return use_case, session_store, gemini_client


def _collect(agen) -> list[str]:
    async def _run() -> list[str]:
        return [chunk async for chunk in agen]

    return asyncio.run(_run())


def test_init_renders_system_instruction_from_professional_history() -> None:
    use_case, _, _ = _make_use_case()

    assert use_case._system_instruction == render_system_instruction(FAKE_HISTORY_DOC)


def test_handle_message_increments_message_count_for_session() -> None:
    use_case, session_store, _ = _make_use_case(stream_chunks=["hi"])

    _collect(use_case.handle_message("abc123", "Hello there"))

    session_store.increment_message_count.assert_awaited_once_with("abc123")


def test_handle_message_reads_history_for_session() -> None:
    use_case, session_store, _ = _make_use_case(stream_chunks=["hi"])

    _collect(use_case.handle_message("abc123", "Hello there"))

    session_store.get_history.assert_awaited_once_with("abc123")


def test_handle_message_passes_system_instruction_history_and_message_to_gemini() -> None:
    stored_history = [ChatTurn(role="user", text="earlier question")]
    use_case, _, gemini_client = _make_use_case(stream_chunks=["hi"], stored_history=stored_history)

    _collect(use_case.handle_message("abc123", "Hello there"))

    gemini_client.generate_stream.assert_called_once_with(
        render_system_instruction(FAKE_HISTORY_DOC), stored_history, "Hello there"
    )


def test_handle_message_yields_gemini_chunks_in_order() -> None:
    use_case, _, _ = _make_use_case(stream_chunks=["Hello", " ", "world"])

    result = _collect(use_case.handle_message("abc123", "Hello there"))

    assert result == ["Hello", " ", "world"]


def test_handle_message_appends_user_turn_after_streaming_completes() -> None:
    use_case, session_store, _ = _make_use_case(stream_chunks=["Hi", " there"])

    _collect(use_case.handle_message("abc123", "Hello there"))

    session_store.append_turn.assert_any_await("abc123", ChatTurn(role="user", text="Hello there"))


def test_handle_message_appends_model_turn_with_joined_reply_chunks() -> None:
    use_case, session_store, _ = _make_use_case(stream_chunks=["Hi", " there"])

    _collect(use_case.handle_message("abc123", "Hello there"))

    session_store.append_turn.assert_any_await("abc123", ChatTurn(role="model", text="Hi there"))


def test_handle_message_appends_user_turn_before_model_turn() -> None:
    use_case, session_store, _ = _make_use_case(stream_chunks=["Hi"])

    _collect(use_case.handle_message("abc123", "Hello there"))

    roles_appended = [call.args[1].role for call in session_store.append_turn.await_args_list]
    assert roles_appended == ["user", "model"]


def test_handle_message_does_not_append_turns_before_stream_is_fully_consumed() -> None:
    """Turns are only persisted once the whole reply has streamed — pulling a
    single chunk from the generator must not trigger a premature append."""
    use_case, session_store, _ = _make_use_case(stream_chunks=["Hi", " there"])

    agen = use_case.handle_message("abc123", "Hello there")
    asyncio.run(agen.__anext__())

    session_store.append_turn.assert_not_awaited()


def test_handle_message_appends_empty_model_turn_when_gemini_yields_nothing() -> None:
    use_case, session_store, _ = _make_use_case(stream_chunks=[])

    result = _collect(use_case.handle_message("abc123", "Hello there"))

    assert result == []
    session_store.append_turn.assert_any_await("abc123", ChatTurn(role="model", text=""))


def test_handle_message_writes_chat_log_record_with_seq_and_joined_reply() -> None:
    writer = MagicMock()
    use_case, _, _ = _make_use_case(
        stream_chunks=["Hi", " there"], chat_log_writer=writer, message_count=7
    )

    before = datetime.now(UTC)
    _collect(use_case.handle_message("abc123", "Hello there"))
    after = datetime.now(UTC)

    writer.write.assert_called_once()
    record = writer.write.call_args.args[0]
    assert isinstance(record, ChatLogRecord)
    assert record.session_id == "abc123"
    assert record.seq == 7
    assert record.user_text == "Hello there"
    assert record.model_text == "Hi there"
    assert record.timestamp.tzinfo is not None
    assert record.timestamp.utcoffset().total_seconds() == 0
    assert before <= record.timestamp <= after


def test_handle_message_without_chat_log_writer_completes_normally() -> None:
    use_case, session_store, _ = _make_use_case(stream_chunks=["Hi"], chat_log_writer=None)

    result = _collect(use_case.handle_message("abc123", "Hello there"))

    assert result == ["Hi"]
    assert session_store.append_turn.await_count == 2


def test_handle_message_chat_log_failure_does_not_break_stream_and_is_logged(caplog) -> None:
    writer = MagicMock()
    writer.write.side_effect = RuntimeError("gcs down")
    use_case, session_store, _ = _make_use_case(stream_chunks=["Hi"], chat_log_writer=writer)

    with caplog.at_level(logging.ERROR):
        result = _collect(use_case.handle_message("abc123", "Hello there"))

    assert result == ["Hi"]
    assert session_store.append_turn.await_count == 2
    assert "Failed to write chat log for session abc123" in caplog.text


def test_handle_message_does_not_write_chat_log_before_stream_is_consumed() -> None:
    writer = MagicMock()
    use_case, _, _ = _make_use_case(stream_chunks=["Hi", " there"], chat_log_writer=writer)

    agen = use_case.handle_message("abc123", "Hello there")
    asyncio.run(agen.__anext__())

    writer.write.assert_not_called()


def test_handle_message_writes_chat_log_after_both_turns_appended() -> None:
    order: list[str] = []
    writer = MagicMock()
    writer.write.side_effect = lambda record: order.append("write")
    use_case, session_store, _ = _make_use_case(stream_chunks=["Hi"], chat_log_writer=writer)
    session_store.append_turn.side_effect = lambda *a: order.append("append")

    _collect(use_case.handle_message("abc123", "Hello there"))

    assert order == ["append", "append", "write"]


def test_message_at_limit_is_allowed() -> None:
    use_case, store, gemini = _make_use_case(["ok"], message_count=5, max_messages=5)

    assert _collect(use_case.handle_message("s1", "hi")) == ["ok"]
    gemini.generate_stream.assert_called_once()
    assert store.append_turn.await_count == 2


def test_message_over_limit_raises_before_any_work() -> None:
    use_case, store, gemini = _make_use_case(["ok"], message_count=6, max_messages=5)

    with pytest.raises(SessionMessageLimitExceeded):
        _collect(use_case.handle_message("s1", "hi"))

    store.get_history.assert_not_called()
    store.append_turn.assert_not_called()
    gemini.generate_stream.assert_not_called()
