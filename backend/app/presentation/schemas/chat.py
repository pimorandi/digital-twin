from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    # Ends up in GCS object names, so restrict it to a safe charset (UUIDs pass).
    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    message: str
