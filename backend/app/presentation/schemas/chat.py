from pydantic import BaseModel, Field

MAX_MESSAGE_CHARS = 2000  # keep in sync with frontend MessageInput's maxLength


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
