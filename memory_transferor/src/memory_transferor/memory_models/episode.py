from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class EpisodeConnection(BaseModel):
    """A directed, validated edge from one episode to another."""

    target_episode_id: str
    relation: str
    confidence: str = "medium"
    score: float = 0.0
    reason: str = ""
    bidirectional_verified: bool = False


class EpisodeGroup(BaseModel):
    """A bounded group of directly connected episodes."""

    group_id: str
    relation: str
    episode_ids: list[str] = Field(default_factory=list)
    seed_episode_id: str = ""
    confidence: str = "medium"
    reason: str = ""


class Episode(BaseModel):
    """Turn-level L2 evidence derived from a RawChatTurn."""

    episode_id: str
    session_id: str
    turn_id: str
    timestamp: datetime | None = None
    summary: str
    keywords: list[str] = Field(default_factory=list)
    source_turn_text: str = ""
    connections: list[EpisodeConnection] = Field(default_factory=list)
    connection_group_ids: list[str] = Field(default_factory=list)
