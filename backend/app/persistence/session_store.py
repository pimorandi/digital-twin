from redis.asyncio import Redis


class RedisSessionStore:
    def __init__(self, client: Redis, ttl_seconds: int) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    async def increment_message_count(self, session_id: str) -> int:
        key = f"session:{session_id}:message_count"
        count = await self._client.incr(key)
        await self._client.expire(key, self._ttl_seconds)
        return count
