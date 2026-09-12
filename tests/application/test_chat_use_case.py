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
from unittest.mock import AsyncMock, MagicMock

from app.application.chat_use_case import ChatUseCase
from app.entities.chat_turn import ChatTurn
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
) -> tuple[ChatUseCase, AsyncMock, MagicMock]:
    session_store = AsyncMock(spec=RedisSessionStore)
    session_store.increment_message_count.return_value = 1
    session_store.get_history.return_value = stored_history or []

    gemini_client = MagicMock(spec=GeminiClient)
    gemini_client.generate_stream = MagicMock(return_value=_fake_stream(stream_chunks or []))

    use_case = ChatUseCase(session_store, gemini_client, FAKE_HISTORY_DOC)
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
