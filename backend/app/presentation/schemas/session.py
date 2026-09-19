from pydantic import BaseModel, Field


class SessionRequest(BaseModel):
    turnstile_token: str = Field(min_length=1, max_length=2048)  # Cloudflare's documented cap


class SessionResponse(BaseModel):
    session_token: str
    expires_in: int
