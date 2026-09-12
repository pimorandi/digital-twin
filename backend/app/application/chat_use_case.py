from collections.abc import AsyncIterator

from app.entities.chat_turn import ChatTurn
from app.entities.prompts import render_system_instruction
from app.infrastructure.gemini_client import GeminiClient
from app.persistence.session_store import RedisSessionStore


class ChatUseCase:
    def __init__(
        self,
        session_store: RedisSessionStore,
        gemini_client: GeminiClient,
        professional_history: str,
    ) -> None:
        self._session_store = session_store
        self._gemini_client = gemini_client
        self._system_instruction = render_system_instruction(professional_history)

    async def handle_message(self, session_id: str, message: str) -> AsyncIterator[str]:
        await self._session_store.increment_message_count(session_id)
        history = await self._session_store.get_history(session_id)

        reply_chunks: list[str] = []
        async for chunk in self._gemini_client.generate_stream(
            self._system_instruction, history, message
        ):
            reply_chunks.append(chunk)
            yield chunk

        await self._session_store.append_turn(session_id, ChatTurn(role="user", text=message))
        await self._session_store.append_turn(
            session_id, ChatTurn(role="model", text="".join(reply_chunks))
        )
