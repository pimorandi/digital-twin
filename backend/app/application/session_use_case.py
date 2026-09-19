from app.application.session_token_service import SessionTokenService
from app.entities.errors import HumanCheckFailed
from app.entities.issued_session import IssuedSession
from app.infrastructure.turnstile_verifier import TurnstileVerifier


class SessionUseCase:
    def __init__(self, verifier: TurnstileVerifier, token_service: SessionTokenService) -> None:
        self._verifier = verifier
        self._token_service = token_service

    async def create_session(self, turnstile_token: str) -> IssuedSession:
        if not await self._verifier.verify(turnstile_token):
            raise HumanCheckFailed("Turnstile verification failed")
        return self._token_service.issue()
