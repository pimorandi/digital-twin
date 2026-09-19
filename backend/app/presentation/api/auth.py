from fastapi import Depends, Header, Request

from app.application.session_token_service import SessionTokenService
from app.entities.errors import InvalidSessionToken


def get_session_token_service(request: Request) -> SessionTokenService:
    return request.app.state.session_token_service


def require_session(
    authorization: str | None = Header(default=None),
    token_service: SessionTokenService = Depends(get_session_token_service),
) -> str:
    """Returns the session id carried by the Bearer token, or raises InvalidSessionToken."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise InvalidSessionToken("Missing bearer token")
    return token_service.verify(token)
