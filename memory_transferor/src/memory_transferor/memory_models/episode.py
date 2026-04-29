from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Episode(BaseModel):
    """Turn-level L2 evidence derived from a RawChatTurn."""

    episode_id: str
    session_id: str
    turn_id: str
    timestamp: datetime | None = None
    summary: str
    keywords: list[str] = Field(default_factory=list)
    source_turn_text: str = ""

