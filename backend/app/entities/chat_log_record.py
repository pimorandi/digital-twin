from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ChatLogRecord:
    session_id: str
    seq: int  # per-instance message counter; resets if the instance restarts
    timestamp: datetime  # timezone-aware, UTC
    user_text: str
    model_text: str
