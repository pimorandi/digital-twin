import json

from redis.asyncio import Redis

from app.entities.chat_turn import ChatTurn


class RedisSessionStore:
    def __init__(self, client: Redis, ttl_seconds: int, max_history_pairs: int) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds
        self._max_history_pairs = max_history_pairs

    async def increment_message_count(self, session_id: str) -> int:
        key = f"session:{session_id}:message_count"
        count = await self._client.incr(key)
        await self._client.expire(key, self._ttl_seconds)
        return count

    async def append_turn(self, session_id: str, turn: ChatTurn) -> None:
        key = f"session:{session_id}:messages"
        await self._client.rpush(key, json.dumps({"role": turn.role, "text": turn.text}))
        await self._client.expire(key, self._ttl_seconds)

    async def get_history(self, session_id: str) -> list[ChatTurn]:
        key = f"session:{session_id}:messages"
        raw_turns = await self._client.lrange(key, -2 * self._max_history_pairs, -1)
        return [ChatTurn(**json.loads(raw)) for raw in raw_turns]
