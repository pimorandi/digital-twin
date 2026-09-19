"""Unit tests for GcsHistoryLoader (backend/app/infrastructure/history_loader.py).

The google.cloud.storage.Client is mocked; no real GCS bucket is required.
download_as_text is a sync method on the real client, so a plain MagicMock is
used rather than an AsyncMock.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app.infrastructure.history_loader import GcsHistoryLoader, parse_gcs_uri


def test_load_from_gcs_returns_downloaded_text() -> None:
    client = MagicMock()
    client.bucket.return_value.blob.return_value.download_as_text.return_value = (
        "# Fake history\nSome fake content."
    )
    loader = GcsHistoryLoader(client, "gs://fake-bucket/fake-path/history.md", None)

    result = loader.load()

    assert result == "# Fake history\nSome fake content."


def test_load_from_gcs_uses_correct_bucket_and_blob_path() -> None:
    client = MagicMock()
    loader = GcsHistoryLoader(client, "gs://fake-bucket/fake-path/history.md", None)

    loader.load()

    client.bucket.assert_called_once_with("fake-bucket")
    client.bucket.return_value.blob.assert_called_once_with("fake-path/history.md")
    client.bucket.return_value.blob.return_value.download_as_text.assert_called_once_with()


def test_load_from_local_fallback_reads_real_file(tmp_path: Path) -> None:
    history_file = tmp_path / "history.md"
    history_file.write_text("# Fake local history\nFake bullet point.", encoding="utf-8")
    loader = GcsHistoryLoader(None, None, str(history_file))

    result = loader.load()

    assert result == "# Fake local history\nFake bullet point."


def test_load_raises_when_neither_gcs_uri_nor_local_path_configured() -> None:
    loader = GcsHistoryLoader(None, None, None)

    with pytest.raises(ValueError, match="Set HISTORY_GCS_URI or HISTORY_LOCAL_PATH"):
        loader.load()


def test_load_prefers_gcs_over_local_fallback_when_both_configured(tmp_path: Path) -> None:
    history_file = tmp_path / "history.md"
    history_file.write_text("# Should never be read", encoding="utf-8")
    client = MagicMock()
    client.bucket.return_value.blob.return_value.download_as_text.return_value = (
        "# Fake GCS history"
    )
    loader = GcsHistoryLoader(client, "gs://fake-bucket/fake-path/history.md", str(history_file))

    result = loader.load()

    assert result == "# Fake GCS history"
    client.bucket.assert_called_once_with("fake-bucket")


def test_load_raises_on_invalid_gcs_scheme() -> None:
    client = MagicMock()
    loader = GcsHistoryLoader(client, "http://example.com/fake-path/history.md", None)

    with pytest.raises(ValueError, match="Invalid GCS URI"):
        loader.load()


def test_parse_gcs_uri_raises_on_non_gs_scheme() -> None:
    with pytest.raises(ValueError, match="Invalid GCS URI"):
        parse_gcs_uri("http://example.com/fake-path/history.md")


def test_parse_gcs_uri_splits_bucket_and_blob_path() -> None:
    bucket_name, blob_path = parse_gcs_uri("gs://fake-bucket/fake-path/history.md")

    assert bucket_name == "fake-bucket"
    assert blob_path == "fake-path/history.md"
