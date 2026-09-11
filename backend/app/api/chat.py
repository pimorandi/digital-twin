import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas.chat import ChatRequest

router = APIRouter()

FIXED_RESPONSE = (
    "Hello! I'm a placeholder response — the digital twin backend is running, "
    "but isn't wired up to the LLM yet."
)


async def _stream_fixed_response() -> AsyncIterator[str]:
    for word in FIXED_RESPONSE.split(" "):
        yield f"data: {word} \n\n"
        await asyncio.sleep(0.05)
    yield "data: [DONE]\n\n"


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream_fixed_response(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
