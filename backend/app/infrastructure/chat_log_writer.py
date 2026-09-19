import json

from google.api_core.exceptions import PreconditionFailed
from google.cloud import storage

from app.entities.chat_log_record import ChatLogRecord
from app.infrastructure.history_loader import parse_gcs_uri


class GcsChatLogWriter:
    """Writes one immutable JSON object per chat exchange under a GCS prefix.

    GCS objects can't be appended to, so each exchange gets its own object;
    create-only writes let the service account hold objectCreator alone.
    """

    def __init__(self, client: storage.Client, gcs_uri: str) -> None:
        self._client = client
        self._bucket_name, prefix = parse_gcs_uri(gcs_uri)
        self._prefix = prefix.strip("/")

    def write(self, record: ChatLogRecord) -> None:
        blob = self._client.bucket(self._bucket_name).blob(self._object_name(record))
        body = json.dumps(
            {
                "session_id": record.session_id,
                "seq": record.seq,
                "timestamp": record.timestamp.isoformat(),
                "user": record.user_text,
                "model": record.model_text,
            },
            ensure_ascii=False,
        )
        try:
            blob.upload_from_string(body, content_type="application/json", if_generation_match=0)
        except PreconditionFailed:
            pass  # object already exists: this exchange was already logged

    def _object_name(self, record: ChatLogRecord) -> str:
        day = record.timestamp.strftime("%Y-%m-%d")
        stamp = record.timestamp.strftime("%Y%m%dT%H%M%S%fZ")
        parts = [self._prefix, day, record.session_id, f"{stamp}_{record.seq:05d}.json"]
        return "/".join(part for part in parts if part)
