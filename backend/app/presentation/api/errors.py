from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.entities.errors import HumanCheckFailed, InvalidSessionToken, SessionMessageLimitExceeded


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(InvalidSessionToken)
    async def _invalid_token(request: Request, exc: InvalidSessionToken) -> JSONResponse:
        return JSONResponse(
            {"detail": "Invalid or expired session"},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(HumanCheckFailed)
    async def _human_check_failed(request: Request, exc: HumanCheckFailed) -> JSONResponse:
        return JSONResponse({"detail": "Human verification failed"}, status_code=403)

    @app.exception_handler(SessionMessageLimitExceeded)
    async def _limit_exceeded(request: Request, exc: SessionMessageLimitExceeded) -> JSONResponse:
        return JSONResponse({"detail": "Message limit reached for this session"}, status_code=429)
