from __future__ import annotations

from pydantic import BaseModel, Field


class PersistentMemoryItem(BaseModel):
    """A stable memory item distilled from episodes."""

    memory_id: str
    type: str
    key: str
    description: str
    evidence_episode_ids: list[str] = Field(default_factory=list)
    evidence_turn_ids: list[str] = Field(default_factory=list)
    confidence: str = "medium"
    scope: str = "persistent"
    export_priority: str = "medium"
    steps: list[str] = Field(default_factory=list)

