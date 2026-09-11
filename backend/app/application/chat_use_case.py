from app.persistence.session_store import RedisSessionStore


class ChatUseCase:
    def __init__(self, session_store: RedisSessionStore) -> None:
        self._session_store = session_store

    async def handle_message(self, session_id: str, message: str) -> int:
        return await self._session_store.increment_message_count(session_id)
