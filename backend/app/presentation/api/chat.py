from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.application.chat_use_case import ChatUseCase
from app.presentation.api.auth import require_session
from app.presentation.schemas.chat import ChatRequest

router = APIRouter()


def get_chat_use_case(request: Request) -> ChatUseCase:
    return request.app.state.chat_use_case


def _sse_frame(chunk: str) -> str:
    return "".join(f"data: {line}\n" for line in chunk.split("\n")) + "\n"


async def _stream_chat(
    first_chunk: str | None, remaining_chunks: AsyncIterator[str]
) -> AsyncIterator[str]:
    if first_chunk is not None:
        yield _sse_frame(first_chunk)
    async for chunk in remaining_chunks:
        yield _sse_frame(chunk)
    yield "data: [DONE]\n\n"


@router.post("/chat/stream")
async def chat_stream(
    chat_request: ChatRequest,
    session_id: str = Depends(require_session),
    chat_use_case: ChatUseCase = Depends(get_chat_use_case),
) -> StreamingResponse:
    chunks = chat_use_case.handle_message(session_id, chat_request.message)
    # Pull the first chunk before creating the response: the message-limit check
    # runs at the start of handle_message, and once StreamingResponse has sent
    # its 200 headers it's too late to turn that into a 429.
    try:
        first_chunk = await anext(chunks)
    except StopAsyncIteration:
        first_chunk = None
    return StreamingResponse(
        _stream_chat(first_chunk, chunks),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
