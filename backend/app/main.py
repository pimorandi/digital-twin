from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from google.cloud import storage
from redis.asyncio import Redis

from app.application.chat_use_case import ChatUseCase
from app.entities.config import load_settings
from app.infrastructure.history_loader import GcsHistoryLoader
from app.persistence.session_store import RedisSessionStore
from app.presentation.api.chat import router as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = load_settings()
    redis_client = Redis.from_url(settings.redis_url)
    session_store = RedisSessionStore(redis_client, settings.session_ttl_seconds)
    app.state.chat_use_case = ChatUseCase(session_store)

    gcs_client = storage.Client() if settings.history_gcs_uri else None
    history_loader = GcsHistoryLoader(
        gcs_client, settings.history_gcs_uri, settings.history_local_path
    )
    app.state.professional_history = history_loader.load()

    yield
    await redis_client.aclose()


app = FastAPI(title="Digital Twin Backend", lifespan=lifespan)
app.include_router(chat_router, prefix="/api")
