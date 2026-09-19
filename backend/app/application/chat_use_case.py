import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from app.entities.chat_log_record import ChatLogRecord
from app.entities.chat_turn import ChatTurn
from app.entities.errors import SessionMessageLimitExceeded
from app.entities.prompts import render_system_instruction
from app.infrastructure.chat_log_writer import GcsChatLogWriter
from app.infrastructure.gemini_client import GeminiClient
from app.persistence.session_store import RedisSessionStore

logger = logging.getLogger(__name__)


class ChatUseCase:
    def __init__(
        self,
        session_store: RedisSessionStore,
        gemini_client: GeminiClient,
        professional_history: str,
        max_messages_per_session: int,
        chat_log_writer: GcsChatLogWriter | None = None,
    ) -> None:
        self._session_store = session_store
        self._gemini_client = gemini_client
        self._system_instruction = render_system_instruction(professional_history)
        self._max_messages_per_session = max_messages_per_session
        self._chat_log_writer = chat_log_writer

    async def handle_message(self, session_id: str, message: str) -> AsyncIterator[str]:
        seq = await self._session_store.increment_message_count(session_id)
        if seq > self._max_messages_per_session:
            raise SessionMessageLimitExceeded(session_id)
        history = await self._session_store.get_history(session_id)

        reply_chunks: list[str] = []
        async for chunk in self._gemini_client.generate_stream(
            self._system_instruction, history, message
        ):
            reply_chunks.append(chunk)
            yield chunk

        reply = "".join(reply_chunks)
        await self._session_store.append_turn(session_id, ChatTurn(role="user", text=message))
        await self._session_store.append_turn(session_id, ChatTurn(role="model", text=reply))
        await self._log_exchange(session_id, seq, message, reply)

    async def _log_exchange(
        self, session_id: str, seq: int, user_text: str, model_text: str
    ) -> None:
        # Awaited inside the request (Cloud Run throttles CPU once the response
        # ends), but a logging failure must never break the chat.
        if self._chat_log_writer is None:
            return
        record = ChatLogRecord(session_id, seq, datetime.now(UTC), user_text, model_text)
        try:
            await asyncio.to_thread(self._chat_log_writer.write, record)
        except Exception:
            logger.exception("Failed to write chat log for session %s", session_id)
