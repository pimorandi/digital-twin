from dataclasses import dataclass


@dataclass(frozen=True)
class ChatTurn:
    role: str  # "user" or "model" — Gemini's own role vocabulary, used as-is
    text: str
