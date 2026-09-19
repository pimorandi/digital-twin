"""Unit tests for TurnstileVerifier; the httpx client is mocked."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from app.infrastructure.turnstile_verifier import TurnstileVerifier


def _client(response=None, error: Exception | None = None) -> AsyncMock:
    client = AsyncMock(spec=httpx.AsyncClient)
    if error is not None:
        client.post.side_effect = error
    else:
        client.post.return_value = response
    return client


def _response(payload=None, json_error: Exception | None = None) -> MagicMock:
    response = MagicMock()
    if json_error is not None:
        response.json.side_effect = json_error
    else:
        response.json.return_value = payload
    return response


def _verify(client: AsyncMock, token: str = "tok") -> bool:
    return asyncio.run(TurnstileVerifier(client, "fake-secret").verify(token))


def test_verify_posts_secret_and_token_without_remoteip() -> None:
    client = _client(_response({"success": True}))

    assert _verify(client, "user-token") is True

    args, kwargs = client.post.call_args
    assert args == ("https://challenges.cloudflare.com/turnstile/v0/siteverify",)
    assert kwargs["data"] == {"secret": "fake-secret", "response": "user-token"}
    assert "remoteip" not in kwargs["data"]


def test_verify_returns_false_when_success_false() -> None:
    assert _verify(_client(_response({"success": False}))) is False


@pytest.mark.parametrize("value", ["true", 1, None])
def test_verify_requires_literal_true(value) -> None:
    assert _verify(_client(_response({"success": value}))) is False


def test_verify_returns_false_when_success_missing() -> None:
    assert _verify(_client(_response({}))) is False


def test_verify_fails_closed_on_http_error() -> None:
    assert _verify(_client(error=httpx.ConnectError("boom"))) is False


def test_verify_fails_closed_on_bad_status() -> None:
    response = _response({"success": True})
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock()
    )
    assert _verify(_client(response)) is False


def test_verify_fails_closed_on_invalid_json() -> None:
    assert _verify(_client(_response(json_error=ValueError("not json")))) is False


def test_verify_works_with_mock_transport() -> None:
    async def run() -> bool:
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"success": True}))
        async with httpx.AsyncClient(transport=transport) as http_client:
            return await TurnstileVerifier(http_client, "s").verify("t")

    assert asyncio.run(run()) is True
