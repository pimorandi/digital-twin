from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.application.chat_use_case import ChatUseCase
from app.presentation.schemas.chat import ChatRequest

router = APIRouter()


def get_chat_use_case(request: Request) -> ChatUseCase:
    return request.app.state.chat_use_case


async def _stream_chat(
    chat_use_case: ChatUseCase, session_id: str, message: str
) -> AsyncIterator[str]:
    async for chunk in chat_use_case.handle_message(session_id, message):
        yield "".join(f"data: {line}\n" for line in chunk.split("\n")) + "\n"
    yield "data: [DONE]\n\n"


@router.post("/chat/stream")
async def chat_stream(
    chat_request: ChatRequest,
    chat_use_case: ChatUseCase = Depends(get_chat_use_case),
) -> StreamingResponse:
    return StreamingResponse(
        _stream_chat(chat_use_case, chat_request.session_id, chat_request.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
