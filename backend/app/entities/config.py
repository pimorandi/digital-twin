import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    redis_url: str
    session_ttl_seconds: int
    history_gcs_uri: str | None
    history_local_path: str | None


def load_settings() -> Settings:
    return Settings(
        redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        session_ttl_seconds=int(os.getenv("SESSION_TTL_SECONDS", "3600")),
        history_gcs_uri=os.getenv("HISTORY_GCS_URI") or None,
        history_local_path=os.getenv("HISTORY_LOCAL_PATH") or None,
    )
