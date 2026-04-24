"""Base memory model with audit fields shared by all memory types."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class EvidenceLink(BaseModel):
    source_type: str  # "l0_raw" | "chat_history" | "l1_signal" | "file" | "user_input"
    source_id: str
    # Human-readable support text. IDs, not excerpts, are the durable index.
    excerpt: str = ""


class MemoryBase(BaseModel):
    """All L2 managed memory objects extend this."""

    id: str = Field(default_factory=_new_id)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    version: int = 1
    evidence_links: list[EvidenceLink] = Field(default_factory=list)
    conflict_log: list[dict[str, Any]] = Field(default_factory=list)
    user_confirmed: bool = False
    # Dominant language for human-facing text in this memory object.
    primary_language: str = ""  # "zh" | "en" | ""
    # IDs of EpisodicMemory objects that contributed to this memory object.
    # For EpisodicMemory itself this is always empty.
    source_episode_ids: list[str] = Field(default_factory=list)
    # Denormalized L0 turn IDs for easier audit/debugging. The episode layer
    # remains the canonical bridge from persistent memory back to raw messages.
    source_turn_refs: list[str] = Field(default_factory=list)

    def touch(self, ts: datetime | None = None) -> None:
        self.updated_at = ts if ts is not None else _now()
        self.version += 1

    def add_evidence(self, source_type: str, source_id: str, excerpt: str = "") -> None:
        candidate = EvidenceLink(source_type=source_type, source_id=source_id, excerpt=excerpt)
        for existing in self.evidence_links:
            if (
                existing.source_type == candidate.source_type
                and existing.source_id == candidate.source_id
                and existing.excerpt == candidate.excerpt
            ):
                return
        self.evidence_links.append(candidate)

    def record_conflict(self, field: str, old_value: Any, new_value: Any, source: str) -> None:
        self.conflict_log.append(
            {
                "timestamp": _now().isoformat(),
                "field": field,
                "old_value": old_value,
                "new_value": new_value,
                "source": source,
                "resolved": False,
            }
        )
