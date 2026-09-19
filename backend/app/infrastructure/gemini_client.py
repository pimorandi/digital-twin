import asyncio
from collections.abc import AsyncIterator

from google import genai
from google.genai import types

from app.entities.chat_turn import ChatTurn

_MAX_ATTEMPTS = 3
_INITIAL_BACKOFF_SECONDS = 1.0


class GeminiClient:
    def __init__(self, client: genai.Client, model: str, max_output_tokens: int) -> None:
        self._client = client
        self._model = model
        self._max_output_tokens = max_output_tokens

    async def generate_stream(
        self, system_instruction: str, history: list[ChatTurn], message: str
    ) -> AsyncIterator[str]:
        contents = [
            types.Content(role=turn.role, parts=[types.Part(text=turn.text)]) for turn in history
        ]
        contents.append(types.Content(role="user", parts=[types.Part(text=message)]))
        config = types.GenerateContentConfig(
            system_instruction=system_instruction, max_output_tokens=self._max_output_tokens
        )

        stream = await self._start_stream_with_backoff(contents, config)
        async for chunk in stream:
            if chunk.text:
                yield chunk.text

    async def _start_stream_with_backoff(
        self, contents: list[types.Content], config: types.GenerateContentConfig
    ):
        backoff = _INITIAL_BACKOFF_SECONDS
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return await self._client.aio.models.generate_content_stream(
                    model=self._model, contents=contents, config=config
                )
            except Exception:
                if attempt == _MAX_ATTEMPTS:
                    raise
                await asyncio.sleep(backoff)
                backoff *= 2
