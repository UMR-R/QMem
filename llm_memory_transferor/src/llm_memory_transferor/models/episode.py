"""Episodic Memory - single conversation or task sprint summary."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field

from .base import MemoryBase


class EpisodicMemory(MemoryBase):
    """
    Records one specific conversation, revision cycle, or milestone.
    Short-to-medium lifespan; provides upgrade evidence for persistent memory.
    """

    episode_id: str = ""
    conv_id: str = ""              # L0 raw session ID this episode was built from
    topic: str = ""                # short title (5-10 words)
    topics_covered: list[str] = Field(default_factory=list)  # all topics in the chat
    platform: str = ""
    time_range_start: Optional[datetime] = None
    time_range_end: Optional[datetime] = None
    summary: str = ""
    key_decisions: list[str] = Field(default_factory=list)
    open_issues: list[str] = Field(default_factory=list)
    turn_refs: list[str] = Field(default_factory=list)
    # Relation flags — which persistent memory categories this episode touches
    relates_to_profile: bool = False
    relates_to_preferences: bool = False
    relates_to_projects: list[str] = Field(default_factory=list)   # project names
    relates_to_workflows: list[str] = Field(default_factory=list)  # workflow names
    promoted_to_persistent: bool = False

    def to_markdown(self) -> str:
        lines = [f"# Episode: {self.topic or self.episode_id}\n"]
        if self.platform:
            lines.append(f"**Platform:** {self.platform}")
        if self.conv_id:
            lines.append(f"**Source Session:** `{self.conv_id}`")
        if self.time_range_start:
            start_str = self.time_range_start.strftime("%Y-%m-%d %H:%M UTC")
            if self.time_range_end:
                end_str = self.time_range_end.strftime("%Y-%m-%d %H:%M UTC")
                lines.append(f"**Period:** {start_str} → {end_str}")
            else:
                lines.append(f"**Period:** {start_str}")
        if self.topics_covered:
            lines.append(f"**Topics:** {', '.join(self.topics_covered)}")
        if self.turn_refs:
            lines.append(f"**Turn Refs:** {', '.join(self.turn_refs[:6])}")
        # Relation flags
        relations = []
        if self.relates_to_profile:
            relations.append("profile")
        if self.relates_to_preferences:
            relations.append("preferences")
        if self.relates_to_projects:
            relations.append(f"projects({', '.join(self.relates_to_projects)})")
        if self.relates_to_workflows:
            relations.append(f"workflows({', '.join(self.relates_to_workflows)})")
        if relations:
            lines.append(f"**Relates to:** {', '.join(relations)}")
        if self.summary:
            lines.append(f"\n## Summary\n{self.summary}")
        if self.key_decisions:
            items = "\n".join(f"- {d}" for d in self.key_decisions)
            lines.append(f"\n## Key Decisions\n{items}")
        if self.open_issues:
            items = "\n".join(f"- [ ] {i}" for i in self.open_issues)
            lines.append(f"\n## Open Issues\n{items}")
        ts = self.created_at.strftime("%Y-%m-%d %H:%M UTC")
        lines.append(f"\n---\n*v{self.version} · created {ts}*")
        return "\n".join(lines)
