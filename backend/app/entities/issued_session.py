from dataclasses import dataclass


@dataclass(frozen=True)
class IssuedSession:
    token: str
    expires_in: int  # seconds
