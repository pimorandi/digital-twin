from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from google import genai
from google.cloud import storage
from redis.asyncio import Redis

from app.application.chat_use_case import ChatUseCase
from app.application.session_token_service import SessionTokenService
from app.application.session_use_case import SessionUseCase
from app.entities.config import load_settings
from app.infrastructure.chat_log_writer import GcsChatLogWriter
from app.infrastructure.gemini_client import GeminiClient
from app.infrastructure.history_loader import GcsHistoryLoader
from app.infrastructure.turnstile_verifier import TurnstileVerifier
from app.persistence.session_store import RedisSessionStore
from app.presentation.api.chat import router as chat_router
from app.presentation.api.errors import register_exception_handlers
from app.presentation.api.session import router as session_router


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
    gemini_client = GeminiClient(genai_client, settings.gemini_model, settings.max_output_tokens)

    chat_log_writer = (
        GcsChatLogWriter(gcs_client, settings.chat_log_gcs_uri)
        if settings.chat_log_gcs_uri
        else None
    )

    app.state.chat_use_case = ChatUseCase(
        session_store,
        gemini_client,
        professional_history,
        settings.max_messages_per_session,
        chat_log_writer,
    )

    http_client = httpx.AsyncClient()
    token_service = SessionTokenService(settings.session_signing_key, settings.session_ttl_seconds)
    app.state.session_token_service = token_service
    app.state.session_use_case = SessionUseCase(
        TurnstileVerifier(http_client, settings.turnstile_secret_key), token_service
    )

    yield
    await http_client.aclose()
    await redis_client.aclose()


app = FastAPI(title="Digital Twin Backend", lifespan=lifespan)
register_exception_handlers(app)
app.include_router(chat_router, prefix="/api")
app.include_router(session_router, prefix="/api")
