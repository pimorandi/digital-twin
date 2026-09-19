from fastapi import APIRouter, Depends, Request

from app.application.session_use_case import SessionUseCase
from app.presentation.schemas.session import SessionRequest, SessionResponse

router = APIRouter()


def get_session_use_case(request: Request) -> SessionUseCase:
    return request.app.state.session_use_case


@router.post("/session")
async def create_session(
    session_request: SessionRequest,
    session_use_case: SessionUseCase = Depends(get_session_use_case),
) -> SessionResponse:
    issued = await session_use_case.create_session(session_request.turnstile_token)
    return SessionResponse(session_token=issued.token, expires_in=issued.expires_in)
