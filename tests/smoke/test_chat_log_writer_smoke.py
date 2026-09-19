"""Smoke test for GcsChatLogWriter against a real GCS bucket.

Skipped unless SMOKE_BUCKET names a bucket the ambient credentials can write to
and read from. Objects are written under the `smoke-tests/` prefix and deleted
afterwards. Run with: SMOKE_BUCKET=<bucket> uv run pytest tests/smoke
"""

import json
import os
import uuid
from datetime import UTC, datetime

import pytest
from app.entities.chat_log_record import ChatLogRecord
from app.infrastructure.chat_log_writer import GcsChatLogWriter

SMOKE_BUCKET = os.getenv("SMOKE_BUCKET")

pytestmark = pytest.mark.skipif(not SMOKE_BUCKET, reason="SMOKE_BUCKET is not set")


def test_write_then_read_back_and_duplicate_write_is_ignored() -> None:
    from google.cloud import storage

    client = storage.Client()
    session_id = f"smoke-{uuid.uuid4().hex}"
    record = ChatLogRecord(
        session_id=session_id,
        seq=1,
        timestamp=datetime.now(UTC),
        user_text="fake smoke question",
        model_text="fake smoke answer",
    )
    writer = GcsChatLogWriter(client, f"gs://{SMOKE_BUCKET}/smoke-tests")
    bucket = client.bucket(SMOKE_BUCKET)
    day = record.timestamp.strftime("%Y-%m-%d")
    prefix = f"smoke-tests/{day}/{session_id}/"

    try:
        writer.write(record)
        writer.write(record)  # same object name: PreconditionFailed must be swallowed

        blobs = list(client.list_blobs(SMOKE_BUCKET, prefix=prefix))
        assert len(blobs) == 1
        assert blobs[0].name.endswith("_00001.json")
        assert json.loads(bucket.blob(blobs[0].name).download_as_text()) == {
            "session_id": session_id,
            "seq": 1,
            "timestamp": record.timestamp.isoformat(),
            "user": "fake smoke question",
            "model": "fake smoke answer",
        }
    finally:
        for blob in client.list_blobs(SMOKE_BUCKET, prefix=prefix):
            blob.delete()
