"""Unit tests for SessionTokenService using an injected fake clock."""

import base64
import json

import pytest
from app.application.session_token_service import SessionTokenService, _b64encode
from app.entities.errors import InvalidSessionToken


class FakeClock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _service(clock: FakeClock, key: str = "fake-key", ttl: int = 60) -> SessionTokenService:
    return SessionTokenService(key, ttl, clock)


def _forge(service: SessionTokenService, body_bytes: bytes) -> str:
    """Correctly signed token around an arbitrary payload."""
    body = _b64encode(body_bytes)
    return f"{body}.{service._sign(body)}"


def test_issue_returns_token_and_ttl() -> None:
    issued = _service(FakeClock()).issue()

    assert issued.expires_in == 60
    assert issued.token.count(".") == 1


def test_issue_generates_distinct_session_ids() -> None:
    service = _service(FakeClock())

    assert service.verify(service.issue().token) != service.verify(service.issue().token)


def test_verify_roundtrip_returns_session_id() -> None:
    service = _service(FakeClock())
    token = service.issue().token

    session_id = service.verify(token)

    assert isinstance(session_id, str) and session_id
    assert service.verify(token) == session_id


def test_verify_default_clock_is_wall_time() -> None:
    service = SessionTokenService("fake-key", 60)

    assert service.verify(service.issue().token)


def test_verify_rejects_token_without_separator() -> None:
    with pytest.raises(InvalidSessionToken):
        _service(FakeClock()).verify("noseparator")


def test_verify_rejects_empty_token() -> None:
    with pytest.raises(InvalidSessionToken):
        _service(FakeClock()).verify("")


def test_verify_rejects_tampered_signature() -> None:
    service = _service(FakeClock())
    body, _, signature = service.issue().token.partition(".")
    flipped = ("A" if signature[0] != "A" else "B") + signature[1:]

    with pytest.raises(InvalidSessionToken):
        service.verify(f"{body}.{flipped}")


def test_verify_rejects_tampered_body() -> None:
    service = _service(FakeClock())
    _, _, signature = service.issue().token.partition(".")
    evil = _b64encode(json.dumps({"sid": "evil", "exp": 10**12}).encode())

    with pytest.raises(InvalidSessionToken):
        service.verify(f"{evil}.{signature}")


def test_verify_rejects_token_signed_with_other_key() -> None:
    clock = FakeClock()
    token = _service(clock, key="key-a").issue().token

    with pytest.raises(InvalidSessionToken):
        _service(clock, key="key-b").verify(token)


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"\xff\xfe",
        b"[]",
        b"null",
        json.dumps({"exp": 2000}).encode(),
        json.dumps({"sid": "x"}).encode(),
    ],
)
def test_verify_rejects_malformed_signed_payload(raw: bytes) -> None:
    service = _service(FakeClock())

    with pytest.raises(InvalidSessionToken, match="Malformed"):
        service.verify(_forge(service, raw))


@pytest.mark.parametrize(
    "payload",
    [
        {"sid": 123, "exp": 2000},
        {"sid": "x", "exp": "2000"},
        {"sid": "x", "exp": None},
    ],
)
def test_verify_rejects_wrong_types(payload) -> None:
    service = _service(FakeClock())

    with pytest.raises(InvalidSessionToken, match="Malformed"):
        service.verify(_forge(service, json.dumps(payload).encode()))


def test_verify_rejects_invalid_base64_body() -> None:
    service = _service(FakeClock())
    body = "!!!!"
    with pytest.raises(InvalidSessionToken):
        service.verify(f"{body}.{service._sign(body)}")


def test_verify_expiry_boundary() -> None:
    clock = FakeClock(1000.0)
    service = _service(clock, ttl=60)
    token = service.issue().token  # exp = 1060

    clock.now = 1059.9
    assert service.verify(token)

    clock.now = 1060.0
    with pytest.raises(InvalidSessionToken, match="expired"):
        service.verify(token)

    clock.now = 2000.0
    with pytest.raises(InvalidSessionToken):
        service.verify(token)


def test_token_body_is_unpadded_urlsafe_base64() -> None:
    body = _service(FakeClock()).issue().token.split(".")[0]

    assert "=" not in body
    payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    assert set(payload) == {"sid", "exp"}
