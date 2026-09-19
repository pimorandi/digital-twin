import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    redis_url: str
    session_ttl_seconds: int
    history_gcs_uri: str | None
    history_local_path: str | None
    chat_log_gcs_uri: str | None
    gcp_project_id: str | None
    vertex_location: str
    gemini_model: str
    max_history_pairs: int
    turnstile_secret_key: str
    session_signing_key: str
    max_messages_per_session: int
    max_output_tokens: int


def _require_env(name: str) -> str:
    # Fail closed: the bot protection must never silently run without its secrets.
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def load_settings() -> Settings:
    return Settings(
        redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        session_ttl_seconds=int(os.getenv("SESSION_TTL_SECONDS", "3600")),
        history_gcs_uri=os.getenv("HISTORY_GCS_URI") or None,
        history_local_path=os.getenv("HISTORY_LOCAL_PATH") or None,
        chat_log_gcs_uri=os.getenv("CHAT_LOG_GCS_URI") or None,
        gcp_project_id=os.getenv("GCP_PROJECT_ID") or None,
        vertex_location=os.getenv("VERTEX_LOCATION", "us-central1"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        max_history_pairs=int(os.getenv("MAX_HISTORY_PAIRS", "10")),
        turnstile_secret_key=_require_env("TURNSTILE_SECRET_KEY"),
        session_signing_key=_require_env("SESSION_SIGNING_KEY"),
        max_messages_per_session=int(os.getenv("MAX_MESSAGES_PER_SESSION", "30")),
        max_output_tokens=int(os.getenv("MAX_OUTPUT_TOKENS", "1024")),
    )
