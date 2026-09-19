import logging

import httpx

logger = logging.getLogger(__name__)

_SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_TIMEOUT_SECONDS = 5.0


class TurnstileVerifier:
    """Verifies a Cloudflare Turnstile token. Fails closed on any error."""

    def __init__(self, http_client: httpx.AsyncClient, secret_key: str) -> None:
        self._http_client = http_client
        self._secret_key = secret_key

    async def verify(self, token: str) -> bool:
        # remoteip is optional and deliberately not sent: client IPs aren't handled here.
        try:
            response = await self._http_client.post(
                _SITEVERIFY_URL,
                data={"secret": self._secret_key, "response": token},
                timeout=_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json().get("success") is True
        except (httpx.HTTPError, ValueError):
            logger.exception("Turnstile verification request failed")
            return False
