"""Unit tests for GcsChatLogWriter (backend/app/infrastructure/chat_log_writer.py).

The google.cloud.storage.Client is mocked; no real GCS bucket is required.
"""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from app.entities.chat_log_record import ChatLogRecord
from app.infrastructure.chat_log_writer import GcsChatLogWriter
from google.api_core.exceptions import NotFound, PreconditionFailed

TS = datetime(2025, 3, 4, 5, 6, 7, 8910, tzinfo=UTC)


def _record(**overrides) -> ChatLogRecord:
    fields = {
        "session_id": "fake-session",
        "seq": 3,
        "timestamp": TS,
        "user_text": "fake question",
        "model_text": "fake answer",
    }
    fields.update(overrides)
    return ChatLogRecord(**fields)


def _write(uri: str, record: ChatLogRecord | None = None) -> MagicMock:
    client = MagicMock()
    GcsChatLogWriter(client, uri).write(record or _record())
    return client


def _object_name(client: MagicMock) -> str:
    return client.bucket.return_value.blob.call_args.args[0]


def test_write_uses_bucket_from_uri() -> None:
    client = _write("gs://fake-bucket/logs")

    client.bucket.assert_called_once_with("fake-bucket")


def test_write_builds_expected_object_name() -> None:
    client = _write("gs://fake-bucket/logs")

    assert _object_name(client) == "logs/2025-03-04/fake-session/20250304T050607008910Z_00003.json"


def test_write_uploads_json_body_with_expected_keys() -> None:
    client = _write("gs://fake-bucket/logs")

    blob = client.bucket.return_value.blob.return_value
    body = blob.upload_from_string.call_args.args[0]
    assert json.loads(body) == {
        "session_id": "fake-session",
        "seq": 3,
        "timestamp": "2025-03-04T05:06:07.008910+00:00",
        "user": "fake question",
        "model": "fake answer",
    }


def test_write_is_create_only_with_json_content_type() -> None:
    client = _write("gs://fake-bucket/logs")

    blob = client.bucket.return_value.blob.return_value
    blob.upload_from_string.assert_called_once()
    kwargs = blob.upload_from_string.call_args.kwargs
    assert kwargs == {"content_type": "application/json", "if_generation_match": 0}


def test_write_preserves_non_ascii_text() -> None:
    client = _write("gs://fake-bucket/logs", _record(user_text="caffè ☕"))

    body = client.bucket.return_value.blob.return_value.upload_from_string.call_args.args[0]
    assert "caffè ☕" in body


@pytest.mark.parametrize(
    "uri",
    ["gs://fake-bucket/logs/", "gs://fake-bucket//logs//", "gs://fake-bucket/logs"],
)
def test_prefix_slashes_are_normalised(uri: str) -> None:
    client = _write(uri)

    assert _object_name(client).startswith("logs/2025-03-04/")


def test_nested_prefix_is_kept() -> None:
    client = _write("gs://fake-bucket/a/b")

    assert _object_name(client).startswith("a/b/2025-03-04/")


@pytest.mark.parametrize("uri", ["gs://fake-bucket", "gs://fake-bucket/"])
def test_empty_prefix_has_no_leading_slash(uri: str) -> None:
    client = _write(uri)

    assert _object_name(client) == "2025-03-04/fake-session/20250304T050607008910Z_00003.json"


def test_seq_is_zero_padded_to_five_digits() -> None:
    client = _write("gs://fake-bucket/logs", _record(seq=42))

    assert _object_name(client).endswith("_00042.json")


def test_precondition_failed_is_swallowed() -> None:
    client = MagicMock()
    blob = client.bucket.return_value.blob.return_value
    blob.upload_from_string.side_effect = PreconditionFailed("exists")

    GcsChatLogWriter(client, "gs://fake-bucket/logs").write(_record())

    blob.upload_from_string.assert_called_once()


def test_other_exceptions_propagate() -> None:
    client = MagicMock()
    client.bucket.return_value.blob.return_value.upload_from_string.side_effect = NotFound("nope")

    with pytest.raises(NotFound):
        GcsChatLogWriter(client, "gs://fake-bucket/logs").write(_record())


def test_invalid_uri_raises_value_error() -> None:
    with pytest.raises(ValueError):
        GcsChatLogWriter(MagicMock(), "http://fake-bucket/logs")
