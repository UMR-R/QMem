from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RawChatTurn(BaseModel):
    """Smallest raw evidence unit: one user-assistant exchange."""

    turn_id: str
    session_id: str
    timestamp: datetime | None = None
    user_text: str = ""
    assistant_text: str = ""
    status: str = "complete"

    def text(self) -> str:
        parts: list[str] = []
        if self.user_text:
            parts.append(f"USER: {self.user_text}")
        if self.assistant_text:
            parts.append(f"ASSISTANT: {self.assistant_text}")
        return "\n".join(parts)


class RawChatSession(BaseModel):
    """One captured chat page/session, grouping raw turns."""

    session_id: str
    platform: str = "unknown"
    title: str = ""
    url: str = ""
    timestamp: datetime | None = None
    turns: list[RawChatTurn] = Field(default_factory=list)

