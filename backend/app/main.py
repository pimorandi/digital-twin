from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from google import genai
from google.cloud import storage
from redis.asyncio import Redis

from app.application.chat_use_case import ChatUseCase
from app.entities.config import load_settings
from app.infrastructure.chat_log_writer import GcsChatLogWriter
from app.infrastructure.gemini_client import GeminiClient
from app.infrastructure.history_loader import GcsHistoryLoader
from app.persistence.session_store import RedisSessionStore
from app.presentation.api.chat import router as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = load_settings()
    redis_client = Redis.from_url(settings.redis_url)
    session_store = RedisSessionStore(
        redis_client, settings.session_ttl_seconds, settings.max_history_pairs
    )

    needs_gcs = settings.history_gcs_uri or settings.chat_log_gcs_uri
    gcs_client = storage.Client() if needs_gcs else None
    history_loader = GcsHistoryLoader(
        gcs_client, settings.history_gcs_uri, settings.history_local_path
    )
    professional_history = history_loader.load()
    app.state.professional_history = professional_history

    genai_client = genai.Client(
        vertexai=True, project=settings.gcp_project_id, location=settings.vertex_location
    )
    gemini_client = GeminiClient(genai_client, settings.gemini_model)

    chat_log_writer = (
        GcsChatLogWriter(gcs_client, settings.chat_log_gcs_uri)
        if settings.chat_log_gcs_uri
        else None
    )

    app.state.chat_use_case = ChatUseCase(
        session_store, gemini_client, professional_history, chat_log_writer
    )

    yield
    await redis_client.aclose()


app = FastAPI(title="Digital Twin Backend", lifespan=lifespan)
app.include_router(chat_router, prefix="/api")
