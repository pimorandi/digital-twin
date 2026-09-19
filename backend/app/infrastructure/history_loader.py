from pathlib import Path
from urllib.parse import urlparse

from google.cloud import storage


class GcsHistoryLoader:
    def __init__(
        self,
        client: storage.Client | None,
        gcs_uri: str | None,
        local_fallback_path: str | None,
    ) -> None:
        self._client = client
        self._gcs_uri = gcs_uri
        self._local_fallback_path = local_fallback_path

    def load(self) -> str:
        if self._gcs_uri:
            bucket_name, blob_path = parse_gcs_uri(self._gcs_uri)
            return self._client.bucket(bucket_name).blob(blob_path).download_as_text()
        if self._local_fallback_path:
            return Path(self._local_fallback_path).read_text(encoding="utf-8")
        raise ValueError("Set HISTORY_GCS_URI or HISTORY_LOCAL_PATH")


def parse_gcs_uri(gcs_uri: str) -> tuple[str, str]:
    parsed = urlparse(gcs_uri)
    if parsed.scheme != "gs":
        raise ValueError(f"Invalid GCS URI: {gcs_uri!r}")
    return parsed.netloc, parsed.path.lstrip("/")
