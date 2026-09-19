import base64
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Callable

from app.entities.errors import InvalidSessionToken
from app.entities.issued_session import IssuedSession


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class SessionTokenService:
    """Issues and verifies stateless HMAC-signed session tokens.

    Token = base64url(json{sid, exp}) + "." + base64url(HMAC-SHA256). Any instance
    holding the signing key can verify it, so no per-instance state is needed.
    """

    def __init__(
        self, signing_key: str, ttl_seconds: int, clock: Callable[[], float] = time.time
    ) -> None:
        self._signing_key = signing_key.encode("utf-8")
        self._ttl_seconds = ttl_seconds
        self._clock = clock

    def issue(self) -> IssuedSession:
        payload = {"sid": str(uuid.uuid4()), "exp": int(self._clock()) + self._ttl_seconds}
        body = _b64encode(json.dumps(payload).encode("utf-8"))
        return IssuedSession(f"{body}.{self._sign(body)}", self._ttl_seconds)

    def verify(self, token: str) -> str:
        """Returns the session id, or raises InvalidSessionToken."""
        body, separator, signature = token.partition(".")
        if not separator or not hmac.compare_digest(signature, self._sign(body)):
            raise InvalidSessionToken("Bad token signature")
        try:
            payload = json.loads(_b64decode(body))
            session_id, expires_at = payload["sid"], payload["exp"]
        except (ValueError, KeyError, TypeError) as error:
            raise InvalidSessionToken("Malformed token payload") from error
        if not isinstance(session_id, str) or not isinstance(expires_at, int):
            raise InvalidSessionToken("Malformed token payload")
        if self._clock() >= expires_at:
            raise InvalidSessionToken("Token expired")
        return session_id

    def _sign(self, body: str) -> str:
        return _b64encode(
            hmac.new(self._signing_key, body.encode("ascii"), hashlib.sha256).digest()
        )
