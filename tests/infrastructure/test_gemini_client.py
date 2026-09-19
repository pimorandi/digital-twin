"""Unit tests for GeminiClient (backend/app/infrastructure/gemini_client.py).

The google.genai Client is fully mocked (`client.aio.models.generate_content_stream`
is an AsyncMock); no real GCP/Vertex AI call is made. `asyncio.sleep` is patched
in the retry tests so the backoff delay never actually elapses.

Coroutines/async generators are driven with `asyncio.run` from plain sync test
functions, matching the pattern already established in this repo's other async
tests (see tests/persistence/test_session_store.py, tests/test_main.py).
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.entities.chat_turn import ChatTurn
from app.infrastructure.gemini_client import GeminiClient
from google.genai import types


def _fake_stream(chunks: list[SimpleNamespace]):
    """Build a real async generator, mirroring what the confirmed-correct SDK
    behavior returns from `await generate_content_stream(...)`."""

    async def _gen():
        for chunk in chunks:
            yield chunk

    return _gen()


def _collect(agen) -> list[str]:
    async def _run() -> list[str]:
        return [chunk async for chunk in agen]

    return asyncio.run(_run())


def test_generate_stream_builds_contents_from_history_and_message() -> None:
    client = MagicMock()
    client.aio.models.generate_content_stream = AsyncMock(
        return_value=_fake_stream([SimpleNamespace(text="hi there")])
    )
    gemini_client = GeminiClient(client, "fake-model", 256)
    history = [ChatTurn(role="user", text="hello"), ChatTurn(role="model", text="hi!")]

    _collect(gemini_client.generate_stream("fake system instruction", history, "how are you?"))

    call_kwargs = client.aio.models.generate_content_stream.call_args.kwargs
    assert call_kwargs["model"] == "fake-model"
    assert call_kwargs["contents"] == [
        types.Content(role="user", parts=[types.Part(text="hello")]),
        types.Content(role="model", parts=[types.Part(text="hi!")]),
        types.Content(role="user", parts=[types.Part(text="how are you?")]),
    ]
    assert call_kwargs["config"] == types.GenerateContentConfig(
        system_instruction="fake system instruction", max_output_tokens=256
    )


def test_generate_stream_with_empty_history_only_appends_message() -> None:
    client = MagicMock()
    client.aio.models.generate_content_stream = AsyncMock(
        return_value=_fake_stream([SimpleNamespace(text="reply")])
    )
    gemini_client = GeminiClient(client, "fake-model", 256)

    _collect(gemini_client.generate_stream("fake system instruction", [], "first message"))

    call_kwargs = client.aio.models.generate_content_stream.call_args.kwargs
    assert call_kwargs["contents"] == [
        types.Content(role="user", parts=[types.Part(text="first message")]),
    ]


def test_generate_stream_yields_chunk_text_in_order() -> None:
    client = MagicMock()
    client.aio.models.generate_content_stream = AsyncMock(
        return_value=_fake_stream([SimpleNamespace(text="Hello"), SimpleNamespace(text=" world")])
    )
    gemini_client = GeminiClient(client, "fake-model", 256)

    result = _collect(gemini_client.generate_stream("system", [], "hi"))

    assert result == ["Hello", " world"]


def test_generate_stream_skips_falsy_chunk_text() -> None:
    client = MagicMock()
    client.aio.models.generate_content_stream = AsyncMock(
        return_value=_fake_stream(
            [
                SimpleNamespace(text="Hello"),
                SimpleNamespace(text=""),
                SimpleNamespace(text=None),
                SimpleNamespace(text=" world"),
            ]
        )
    )
    gemini_client = GeminiClient(client, "fake-model", 256)

    result = _collect(gemini_client.generate_stream("system", [], "hi"))

    assert result == ["Hello", " world"]


def test_generate_stream_retries_after_transient_failure_then_succeeds() -> None:
    client = MagicMock()
    client.aio.models.generate_content_stream = AsyncMock(
        side_effect=[RuntimeError("transient failure"), _fake_stream([SimpleNamespace(text="ok")])]
    )
    gemini_client = GeminiClient(client, "fake-model", 256)

    with patch("app.infrastructure.gemini_client.asyncio.sleep", new=AsyncMock()) as fake_sleep:
        result = _collect(gemini_client.generate_stream("system", [], "hi"))

    assert result == ["ok"]
    assert client.aio.models.generate_content_stream.await_count == 2
    fake_sleep.assert_awaited_once_with(1.0)


def test_generate_stream_backoff_doubles_between_retries() -> None:
    client = MagicMock()
    client.aio.models.generate_content_stream = AsyncMock(
        side_effect=[
            RuntimeError("first failure"),
            RuntimeError("second failure"),
            _fake_stream([SimpleNamespace(text="ok")]),
        ]
    )
    gemini_client = GeminiClient(client, "fake-model", 256)

    with patch("app.infrastructure.gemini_client.asyncio.sleep", new=AsyncMock()) as fake_sleep:
        _collect(gemini_client.generate_stream("system", [], "hi"))

    assert [call.args[0] for call in fake_sleep.await_args_list] == [1.0, 2.0]


def test_generate_stream_gives_up_after_exhausting_attempts() -> None:
    client = MagicMock()
    client.aio.models.generate_content_stream = AsyncMock(
        side_effect=[
            RuntimeError("failure 1"),
            RuntimeError("failure 2"),
            RuntimeError("failure 3"),
        ]
    )
    gemini_client = GeminiClient(client, "fake-model", 256)

    with (
        patch("app.infrastructure.gemini_client.asyncio.sleep", new=AsyncMock()),
        pytest.raises(RuntimeError, match="failure 3"),
    ):
        _collect(gemini_client.generate_stream("system", [], "hi"))

    assert client.aio.models.generate_content_stream.await_count == 3
